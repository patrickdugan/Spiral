"""One owned 2,000-sat inbound payment against the pre-funded two-leaf pool.

No uncertain send is retried. Captures the accepted HTLC before allowing the
client to claim. Errors cancel the hold invoice, then preserve terminal evidence.
"""
import json
import subprocess
import time
from bootstrap import DOCKER, core
from launch import bark
from fund import cln
from attest import save, DEST
from observe import snapshot, redact
from pay import action


def main():
    if core('getblockchaininfo')['chain'] != 'regtest':
        raise RuntimeError('owned regtest required')
    if (DEST / 'action-inbound-invoice-2000.json').exists():
        raise RuntimeError('invoice already attempted; inspect instead of retry')
    snapshot('inbound-before')
    invoice = action('inbound-invoice-2000', lambda: json.loads(bark('lightning', 'invoice', '2000sat').stdout))['invoice']
    decoded = cln('peer', 'decode', invoice)
    payment_hash = decoded['payment_hash']
    save('inbound-invoice-decoded.json', redact(decoded))
    start = time.monotonic_ns()
    save('action-inbound-peer-pay-2000.json', {'state': 'intent', 'payment_hash': payment_hash,
        'amount_sat': 2000, 'monotonic_start_ns': start, 'height': core('getblockcount')})
    process = subprocess.Popen([*DOCKER, 'exec', 'spiral-cln-peer', 'lightning-cli', '--network=regtest', '--lightning-dir=/data',
        '--json', '--notifications=none', '-k', 'pay', f'bolt11={invoice}', 'retry_for=60'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    claimed = False
    try:
        for _ in range(45):
            held = redact(cln('server', 'listholdinvoices', payment_hash))
            if any(c.get('htlcs') for c in cln('server', 'listpeerchannels')['channels']):
                save('inbound-held-invoice.json', {'monotonic_observed_ns': time.monotonic_ns(), 'hold': held})
                break
            if process.poll() is not None:
                raise RuntimeError('peer payment terminated before an HTLC was observed')
            time.sleep(1)
        else:
            raise RuntimeError('accepted HTLC not observed within bound')
        snapshot('inbound-accepted')
        save('inbound-peer-accepted.json', cln('peer', 'listpeerchannels'))
        action('inbound-claim-2000', lambda: {'exit_code': bark('lightning', 'claim', payment_hash, '--wait', '--no-sync').returncode})
        claimed = True
        stdout, stderr = process.communicate(timeout=60)
        result = redact(json.loads(stdout)) if stdout.strip() else None
        save('action-inbound-peer-pay-2000.json', {'state': 'returned', 'payment_hash': payment_hash,
            'amount_sat': 2000, 'monotonic_start_ns': start, 'monotonic_end_ns': time.monotonic_ns(),
            'exit_code': process.returncode, 'result': result, 'stderr': stderr})
        snapshot('inbound-settled')
        save('inbound-peer-settled.json', cln('peer', 'listpeerchannels'))
        save('inbound-hold-settled.json', redact(cln('server', 'listholdinvoices', payment_hash)))
    finally:
        if not claimed:
            # One targeted cancellation; a failed collection never triggers a resend.
            action('inbound-error-cancel', lambda: cln('server', 'cancelholdinvoice', payment_hash))
            stdout, stderr = process.communicate(timeout=60)
            save('inbound-error-pay-result.json', {'exit_code': process.returncode,
                'result': redact(json.loads(stdout)) if stdout.strip() else None, 'stderr': stderr})


if __name__ == '__main__':
    main()
