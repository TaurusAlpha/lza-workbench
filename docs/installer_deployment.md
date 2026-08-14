# Installer deployment sequence

`lza installer deploy` performs the following stages in order. Each stage stops the
workflow on failure; no later mutation occurs.

| Stage | Activity | Effect | Failure outcome |
| --- | --- | --- | --- |
| Workspace | Load a configured workspace and operational state. | Read-only | A readiness error explains the missing workspace prerequisite. |
| Preflight | Check required installer configuration fields. | Read-only | Lists missing fields and stops before AWS access. |
| AWS identity | Resolve the configured execution context and verify the expected account. | Read-only AWS | Stops before source or CloudFormation activity. |
| Template | Resolve the installer template and validate generated CloudFormation parameters. | Local read-only | Stops before AWS mutation. |
| Source | Inspect CodeCommit or the configured S3 bucket and object key. | Read-only AWS | CodeCommit must already contain its selected branch; S3 must already contain its selected object. Both are manual prerequisites. |
| CloudFormation plan | Inspect stack parameters and stack state. | Read-only AWS | Unknown, transitional, failed, or otherwise unsafe states are rejected. |
| Presentation | Render the planned operation and parameter changes. | Terminal output | Does not alter local files or AWS. |
| Confirmation | Ask for approval unless `--force` or `--dry-run` is used. | Terminal input | Cancellation exits without mutation. |
| Deployment | Create or update the stack and stream events. | AWS mutation | CloudFormation reports the terminal failure; state is not changed. |
| State | Record identity and successful stack data in `.lza/state.json`. | Local file mutation | Runs only after `CREATE_COMPLETE` or `UPDATE_COMPLETE`. |

`--dry-run` completes through planning and presentation only. It does not create a
source bucket or repository, deploy CloudFormation, or write `.lza/state.json`.
