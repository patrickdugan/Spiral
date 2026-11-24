"""Apply the overnight telemetry changes to the checked-out desktop branch."""
from pathlib import Path


repo = Path(r"C:\Users\patri\OneDrive\Documents\GitHub\rbzk-prover-ui")


def edit(name, changes):
    path = repo / name
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    for previous, after in changes:
        if text.count(previous) != 1:
            raise ValueError(f"application source changed at {name}")
        text = text.replace(previous, after, 1)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


edit("prover-ui/src/server.rs", [
    ('''    if raw["cleanup"] == "vm_deleted" {
        sample["active"] = json!(false);
        sample["stage"] = json!("stopped");
''', '''    if raw["cleanup"] == "vm_deleted" {
        let local_stage = match stage {
            "overnight_sdk_m13_verification" => Some(("verify_sdk_m13", true)),
            "overnight_m14_evaluation" if raw["sdk_m13_independent_exit"] == 0 => {
                Some(("verify_m14", true))
            }
            "overnight_offchain_proof_verified"
                if raw["sdk_m13_independent_exit"] == 0 && raw["m14_independent_exit"] == 0 =>
            {
                Some(("proof_checks_passed", false))
            }
            "overnight_verification_failed" => Some(("verification_failed", false)),
            _ => None,
        };
        if let Some((phase, active)) = local_stage {
            sample["stage"] = json!(phase);
            sample["active"] = json!(active);
            sample["local_verification"] = json!(true);
        } else {
            sample["active"] = json!(false);
            sample["stage"] = json!("stopped");
        }
'''),
    ('''            "preparing_inputs" => "preparing",''', '''            "preparing_inputs" => match raw["prepare_phase"].as_str() {
                Some("public_base") => "restoring_public_checkpoint",
                Some("private_seed") => "restoring_private_checkpoint",
                Some("export") => "checking_checkpoint_export",
                _ => "preparing",
            },'''),
    ('''        let ended = read_hyperstack_ark_state(&path, None).context("ended pilot state was discarded")?;
        std::fs::remove_file(path)?;
        assert_eq!(ended["active"], false);
        assert_eq!(ended["stage"], "stopped");''', '''        let ended = read_hyperstack_ark_state(&path, None).context("ended pilot state was discarded")?;
        assert_eq!(ended["active"], false);
        assert_eq!(ended["stage"], "stopped");

        state["cleanup"] = Value::Null;
        state["stage"] = json!("preparing_inputs");
        state["prepare_phase"] = json!("private_seed");
        std::fs::write(&path, serde_json::to_vec(&state)?)?;
        let restoring = read_hyperstack_ark_state(&path, None).context("missing restore phase")?;
        assert_eq!(restoring["stage"], "restoring_private_checkpoint");

        state["cleanup"] = json!("vm_deleted");
        state["stage"] = json!("overnight_m14_evaluation");
        state["sdk_m13_independent_exit"] = json!(0);
        std::fs::write(&path, serde_json::to_vec(&state)?)?;
        let local = read_hyperstack_ark_state(&path, None).context("missing local verification")?;
        assert_eq!(local["active"], true);
        assert_eq!(local["stage"], "verify_m14");
        assert_eq!(local["local_verification"], true);
        assert!(local.get("ark_running").is_none());

        state["stage"] = json!("overnight_offchain_proof_verified");
        std::fs::write(&path, serde_json::to_vec(&state)?)?;
        let incomplete = read_hyperstack_ark_state(&path, None).context("missing terminal state")?;
        assert_eq!(incomplete["stage"], "stopped");
        state["m14_independent_exit"] = json!(0);
        std::fs::write(&path, serde_json::to_vec(&state)?)?;
        let complete = read_hyperstack_ark_state(&path, None).context("missing checked state")?;
        std::fs::remove_file(path)?;
        assert_eq!(complete["stage"], "proof_checks_passed");
        assert_eq!(complete["active"], false);'''),
])

edit("prover-ui/web/app.js", [
    ('''    const {connected, paused, processObserved, setupRecorded, coreSource, plan = {}} = options;''', '''    const {connected, paused, processObserved, setupRecorded, coreSource, overnight, plan = {}} = options;'''),
    ('''    const latestStatus = typeof wsl.status === 'string' ? wsl.status : 'unknown';''', '''    const observedLocalStage = {verify_sdk_m13:'sdk-verify',verify_m14:'m14claim',proof_checks_passed:'all_proof_checks_passed'}[overnight?.stage];
    const latestStatus = observedLocalStage || (typeof wsl.status === 'string' ? wsl.status : 'unknown');'''),
    ('''    const checksPassed = phase === 'all_proof_checks_passed' && wsl.compressed_exists === true && wsl.wrap_v2_exists === true;''', '''    const checksPassed = phase === 'all_proof_checks_passed' &&
      (observedLocalStage === phase || (wsl.compressed_exists === true && wsl.wrap_v2_exists === true));'''),
    ('''    const phaseObserved = connected && (current?.id === 'sp1' ? processObserved :''', '''    const phaseObserved = observedLocalStage ? overnight.fresh === true :
      connected && (current?.id === 'sp1' ? processObserved :'''),
    ('''      const activity=sample.ark_running?'Running':''', '''      const activity=sample.local_verification?'Verifying':sample.ark_running?'Running':'''),
    ('''      rows.push({id:'cloud-ark',title:'Ark SP1 prover',where:staging?'Hyperstack · private storage':'Hyperstack · A100 GPU',''', '''      rows.push({id:'cloud-ark',title:sample.local_verification?'Ark proof verification':'Ark SP1 prover',
        where:sample.local_verification?'Local machine · CPU':staging?'Hyperstack · private storage':'Hyperstack · A100 GPU','''),
    ('''        details:'#shard-panel',detailsLabel:'Checkpoint details',metrics:staging?[''', '''        details:'#shard-panel',detailsLabel:sample.local_verification?'Verification details':'Checkpoint details',metrics:staging?['''),
    ('''    const cloud=arkCloudSignal(), trend=ProofEta.checkpointTrend(checkpointHistory);
    const coreSource''', '''    const cloud=arkCloudSignal(), trend=ProofEta.checkpointTrend(checkpointHistory);
    const overnight=cloud?.sample.local_verification?{stage:cloud.sample.stage,fresh:cloud.fresh}:null;
    const coreSource'''),
    ('''    const forecastConnected=coreSource?.connected ?? connected;
    const campaign=ProofEta.arkCampaign(wsl,{connected,paused:!state.polling,processObserved,setupRecorded,coreSource,plan:campaignPlan});''', '''    const campaignConnected=connected || overnight?.fresh === true;
    const forecastConnected=coreSource?.connected ?? campaignConnected;
    const campaign=ProofEta.arkCampaign(wsl,{connected:campaignConnected,paused:!state.polling,
      processObserved,setupRecorded,coreSource,overnight,plan:campaignPlan});'''),
    ('''      provisioning:'Provisioning A100',preparing:'Downloading checkpoint copy',starting:'Starting prover',
      replay:''', '''      provisioning:'Provisioning A100',preparing:'Verifying the pinned GPU kit',
      restoring_public_checkpoint:'Restoring the public checkpoint',
      restoring_private_checkpoint:'Restoring the private checkpoint delta',
      checking_checkpoint_export:'Checking durable checkpoint storage',starting:'Starting prover',
      verify_sdk_m13:'Independently verifying SP1 and M13',verify_m14:'Evaluating and testing BitVM3',
      proof_checks_passed:'Independent proof checks passed',verification_failed:'Local proof verification failed',
      replay:'''),
    ('''    const boot=['staging','queued','waiting_stock','provisioning','preparing'].includes(sample.stage);''', '''    const boot=['staging','queued','waiting_stock','provisioning','preparing','restoring_public_checkpoint',
      'restoring_private_checkpoint','checking_checkpoint_export'].includes(sample.stage);'''),
    ('''      active:sample.active&&fresh&&Number.isSafeInteger(sample.vm_id)};''', '''      active:sample.active&&fresh&&!sample.local_verification&&Number.isSafeInteger(sample.vm_id)};'''),
    ('''    $('shard-heading').textContent='ARK SP1 · HYPERSTACK SHARDING';''', '''    $('shard-heading').textContent=sample.local_verification?'ARK · LOCAL VERIFICATION':'ARK SP1 · HYPERSTACK SHARDING';'''),
])
