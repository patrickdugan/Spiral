//! Valueless fixture setup; never run this helper against an existing wallet.
use cdk_payment_processor_bark::{backend::BarkBackend, settings::Config};
use std::io::Read;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cfg = Config::from_env()?;
    anyhow::ensure!(
        cfg.bark.network == "regtest",
        "fixture helper requires regtest"
    );
    anyhow::ensure!(
        cfg.bark.bitcoind_address.is_some(),
        "fixture helper requires the local Core profile"
    );
    let mut args = std::env::args().skip(1);
    let operation = args.next().unwrap_or_else(|| "status".into());
    let amount = args
        .next()
        .map(|s| s.parse::<u64>())
        .transpose()?
        .unwrap_or(0);
    anyhow::ensure!(args.next().is_none(), "unexpected argument");
    if operation == "seed" {
        anyhow::ensure!(amount == 0, "seed does not accept an amount");
        let mut entropy = [0u8; 32];
        std::fs::File::open("/dev/urandom")?.read_exact(&mut entropy)?;
        let mnemonic = bip39::Mnemonic::from_entropy(&entropy)?;
        println!("{}", serde_json::json!({"mnemonic": mnemonic.to_string()}));
        return Ok(());
    }
    let backend = BarkBackend::new(&cfg.bark).await?;
    println!("{}", backend.regtest_liquidity(&operation, amount).await?);
    Ok(())
}
