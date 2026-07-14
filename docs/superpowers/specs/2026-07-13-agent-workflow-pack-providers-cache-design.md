# Agent Workflow Pack Providers and Secure Cache Design

**Status:** Approved
**Approval:** Covered by explicit user blanket approval on 2026-07-13 after successful self-review
**Dependency:** Approved Core Schemas and Resolver feature spec
**Implementation gate:** No implementation until the Providers/Cache implementation plan is separately approved

## 1. Scope and Non-goals

This feature owns provider planning, acquisition, verification, cache publication, third-party initializer containment, direct-human provider exception approval, broker release evidence, attempt recovery, deterministic candidate-output validation, and provider provenance.

It does not write the target project, construct reconcile transactions, change task state, calculate routes, generate platform adapters, or publish releases. Provider output is candidate evidence consumed by Task 3. Cache and attempt evidence never become project, routing, approval, or supply-chain authority.

Imported frozen interfaces:

| Interface | Producer content commit | Registry commit | Imported digest |
|---|---|---|---|
| core.schema-catalog.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |
| core.errors.v1 | 2e0bfda7619223397f7c9610d312a2aab42156ab | 14edc566f707bb6ad21c551f1112b7c4f543330c | a6a850994705d115e82f0ff1660e1136581a991996b51fa7fa606963879b8c77 |

## 2. Provider Interface and Acquisition Result

### 2.1 Provider plan

Before third-party execution, the caller constructs:

~~~yaml
schema_id: agent-workflow.provider-plan
schema_version: 1
provider_id: trellis-initializer
provider_version: locked-version
provider_artifact_digest: 64-lowercase-hex
command_digest: 64-lowercase-hex
command:
  executable_id: locked-provider-entry
  arguments: []
project_id: canonical-uuid
workspace_instance_id: canonical-uuid
workflow_lock_digest: 64-lowercase-hex
input_digests: []
requested_controls: {}
measured_isolation_gaps: []
approval_challenge: 256-bit-value
prospective_transaction_id: canonical-uuid
deterministic_output_contract: {}
~~~

The plan excludes target-project write paths, ambient environment, caller URLs, unverified executable paths, secrets, and final reconcile-plan identity. provider_plan_digest is domain-separated SHA-256 over the normalized closed object.

### 2.2 Provider callable

~~~text
acquire(request: AcquisitionRequest) -> AcquisitionResult | ProviderFailure
execute_provider(plan: ProviderPlan, approval: ProviderApproval | null)
  -> ProviderExecutionResult | ProviderFailure
~~~

AcquisitionRequest identifies one workflow-lock object, expected complete byte hash, download size limit, cache namespace, archive policy, and source URL already authorized by the correct supply-chain authority. Providers cannot reinterpret or replace those identities.

AcquisitionResult contains:

- verified source identity and complete archive hash;
- cache object identity and immutable published path;
- archive/member validation evidence;
- extracted content-root digest when extraction is requested;
- sanitized diagnostics digest;
- provenance and license records;
- no target-project mutation.

ProviderExecutionResult contains one terminal attempt identity, containment evidence, sanitized result category, validated candidate-output root, and provenance. Unvalidated output is never returned as a render candidate.

## 3. Cache Namespace, Locks, and Atomic Publication

### 3.1 Namespaces

The user cache uses distinct roots:

~~~text
agent-workflow-pack/
  objects/sha256/aa/full-digest
  extracted/sha256/aa/full-digest
  quarantine/uuid
  provider-attempts/workspace-id/provider-plan-digest.json
  provider-attempts/workspace-id/provider-plan-digest.releases/attempt-id.json
  locks/object-digest.lock
  locks/provider-plan-digest.lock
~~~

Cache paths are derived only from validated lowercase SHA-256, canonical UUID, and fixed path grammar. Caller filenames never become cache path segments.

### 3.2 Lock order

One cache-object lock serializes download, verification, quarantine, extraction, and atomic promotion for an object. One provider-plan lock serializes attempt state and remains held from recovery inspection through terminal attempt replacement.

The provider-plan lock may acquire cache-object locks for already authorized inputs. Cache publication code may not acquire a provider-plan lock. This direction prevents lock cycles.

### 3.3 Atomic publication

1. create a same-filesystem private temporary path;
2. stream bytes while enforcing the compressed-size limit and hashing;
3. fsync/close according to the supported filesystem contract;
4. validate the complete expected hash;
5. validate archive format and members if applicable;
6. atomically rename to the digest-derived final path under lock;
7. reject an existing final object unless its type, bytes, and hash match exactly.

Partial, wrong-hash, wrong-type, symlinked, or collision-ambiguous entries move to quarantine under the lock and are never reused automatically.

## 4. Download Limits, Hash-Before-Parse, and Archive Safety

The complete archive byte hash must match the workflow lock before format detection, member enumeration, decompression, parsing, or extraction. Exceeding the compressed-download limit aborts before hash completion and rejects the object.

Redirects revalidate HTTPS, allowed host, port, userinfo absence, redirect count, and policy-authorized destination. URL userinfo and secret-bearing query values never enter diagnostics.

Archive validation rejects:

- absolute, traversal, empty, dot, dot-dot, device, or normalization-ambiguous paths;
- symlinks, hardlinks, devices, FIFOs, sockets, and unsupported entry types;
- duplicate paths and case-folded or Unicode-normalized collisions;
- setuid, setgid, unsafe executable modes, and unsupported mode bits;
- excess member count, single-file size, expanded size, depth, or compression ratio;
- members outside the extraction root after normalized joining.

Extraction creates only regular files and declared directories in a new private root. Candidate content hashing binds normalized relative path, regular-file bytes, and normalized POSIX mode in stable path order.

## 5. Provider Security Policy and Capability Outcomes

Each control has one policy level:

| Level | Meaning |
|---|---|
| required | unavailable or failed enforcement blocks |
| approval-required | unavailable enforcement requires a valid direct-human exception for the exact provider plan |
| best-effort | attempt and report; absence alone does not block |

The baseline required controls are temporary HOME/XDG, environment allowlist, secret stripping, closed stdin, target-path isolation, timeout/output limits, archive/cache integrity, and baseline process/memory/CPU limits. Network isolation is approval-required when enforceable isolation is unavailable. Enhanced namespace, seccomp, or container containment is best-effort unless a profile raises it.

MeasuredCapabilityOutcome records control ID, requested level, observed level, enforcement mechanism ID/version, evidence digest, and failure reason. Unavailable is never reported as enforced.

The execution environment contains only:

- fixed locale and timezone;
- fixed HOME/XDG temporary paths;
- allowlisted non-secret variables with normalized values;
- closed stdin;
- explicit working directory unrelated to the target project;
- exact command vector from the plan;
- bounded stdout/stderr capture;
- recorded umask and resource limits.

Tokens, SSH agent, cloud credentials, proxy credentials, user config, hostname, username, ambient clock, randomness, temporary-root spelling, and filesystem enumeration order cannot influence managed output.

## 6. Direct-Human Provider Exception Approval

Provider approval is a closed branch distinct from task approval:

~~~yaml
schema_id: agent-workflow.provider-approval
schema_version: 1
approval_id: canonical-uuid
verifier_id: platform-approval-verifier
verifier_version: 1.0.0
platform: codex
harness_version: pinned-version
actor:
  id: platform-human-actor-id
  kind: direct-human
issued_at: UTC-RFC3339
expires_at: UTC-RFC3339
workspace_instance_id: canonical-uuid
operation: approve-provider-execution
provider_plan_digest: 64-lowercase-hex
risk_report_digest: 64-lowercase-hex
prospective_transaction_id: canonical-uuid
approval_challenge: 256-bit-value
verifier_receipt: opaque-enforced-verifier-value
~~~

The verifier must authenticate operation and every bound field through a platform CapabilityManifest proving provider_exception_approval enforced. Model-authored input, terminal flags, task approval fields, or instruction-only confirmation cannot authorize execution.

One approval authorizes serialized, auditable retries of one immutable provider plan within its validity window. Changed provider/version, command, input, controls, workspace, prospective transaction, risk report, or expired approval requires a new proof. It does not promise exactly one process invocation.

## 7. Trusted Broker Handshake and Attempt Journal

### 7.1 Whole-file attempt journal

~~~json
{
  "schema_id": "agent-workflow.provider-attempts",
  "schema_version": 1,
  "workspace_instance_id": "canonical-uuid",
  "provider_plan_digest": "64-lowercase-hex",
  "prospective_transaction_id": "canonical-uuid",
  "approval_digest": "64-lowercase-hex-or-canonical-null",
  "attempts": []
}
~~~

The journal is read and schema-validated as one object, changed in memory, and committed by same-filesystem whole-file atomic replacement under the plan lock. Byte append is forbidden.

Attempt states are:

~~~text
prepared -> released -> succeeded | failed | interrupted
prepared -> interrupted
~~~

No attempt ID repeats and attempts for one plan never overlap.

### 7.2 Broker preparation

The parent starts a first-party broker in a new process group or containment unit with private control and acknowledgement pipes. Before release, the broker:

- imports no provider module or initializer entry;
- receives no provider arguments or third-party code;
- arms a Linux/WSL parent-death signal and rechecks expected parent identity;
- enforces a monotonic release deadline;
- exits on parent EOF, parent death, malformed/duplicate frame, or deadline.

The parent creates a fresh release token. The prepared record binds only the token digest, attempt ID, broker liveness identity, timestamps/deadline, command digest, and isolation measurements. The parent durably writes prepared before sending the token.

### 7.3 Release receipt

The broker accepts one framed token, verifies its digest, and atomically creates an immutable receipt at the attempt-specific release path:

~~~json
{
  "schema_id": "agent-workflow.provider-release-receipt",
  "schema_version": 1,
  "workspace_instance_id": "canonical-uuid",
  "provider_plan_digest": "64-lowercase-hex",
  "prospective_transaction_id": "canonical-uuid",
  "attempt_id": "canonical-uuid",
  "release_token_digest": "64-lowercase-hex",
  "broker_liveness_identity": "platform-bounded-identity",
  "released_at": "UTC-RFC3339"
}
~~~

The receipt has an original-absence precondition and is never replaced or deleted for retry. After creating it, the broker acknowledges, closes the control channel, and only then loads provider code. The parent advances the whole journal to released only after validating receipt and acknowledgement.

### 7.4 Terminal state

The parent records succeeded or failed with exit category, sanitized-output digest, and validated candidate-output digest. released becomes interrupted only after positive evidence that the complete containment ended. prepared becomes interrupted only when receipt absence and positive broker/containment termination are established.

PID reuse, live or ambiguous containment, mismatched/missing receipt after possible release, illegal state, corrupt JSON, duplicate token/attempt, or plan/approval mismatch blocks retry.

## 8. Deterministic Initializer Output Contract

Every materializing initializer binds:

~~~yaml
schema_id: agent-workflow.initializer-output-contract
schema_version: 1
provider_id: stable-provider-id
provider_version: locked-version
command_digest: 64-lowercase-hex
input_digests: []
locale: C.UTF-8
timezone: UTC
environment: {}
umask: "0022"
mode_policy_id: posix-mode-v1
file_order_policy_id: normalized-path-order-v1
renderer_id: stable-renderer-id
renderer_version: 1
expected_content_root_digest: 64-lowercase-hex
~~~

The validator rejects ambient time, random, host/user, absolute temporary path, nondeterministic enumeration, or unnormalized metadata in managed output. A schema-defined normalization may remove only explicitly named nonsemantic fields before hashing.

Release CI executes the initializer at least twice in independent clean roots and requires identical validated content roots. Runtime output must equal the lock/artifact-bound expected root. A mismatch is AWP_INITIALIZER_NONDETERMINISTIC and cannot become an ordinary reconcile diff.

## 9. Provenance, Licenses, and Notices

Every acquired, extracted, generated, modified, or vendored third-party unit records:

~~~yaml
schema_id: agent-workflow.provenance-record
schema_version: 1
component_id: stable-component-id
source_artifact:
  version: locked-version
  source_digest: 64-lowercase-hex
  upstream_path: normalized-upstream-path
license_expression: SPDX-expression
license_text_digest: 64-lowercase-hex
modified: true
modification_notice_digest: 64-lowercase-hex
projected_unit_ids: []
~~~

The exact pinned upstream metadata and license text are revalidated. Component-name assumptions are forbidden. Vendored Python remains third-party content. THIRD_PARTY_NOTICES is generated from the selected closure, and target notices cover only content actually projected while remaining complete for that content.

## 10. Failure Recovery and Retry Semantics

Recovery under the provider-plan lock follows:

| Observed state | Permitted recovery |
|---|---|
| no journal | start only after plan/approval validation |
| prepared, no receipt, broker positively gone | record interrupted; retry if approval still valid |
| prepared, receipt present | record released; inspect containment |
| prepared, containment live/ambiguous | block |
| released, containment live/ambiguous | block |
| released, containment positively ended without terminal result | record interrupted; discard output |
| failed/interrupted | retry only unchanged plan and unexpired approval |
| succeeded | reuse only validated result for the same prospective transaction |
| corrupt/illegal/mismatched evidence | fail closed; do not truncate or recreate |

Cache quarantine, journal repair, and receipt inspection never delete audit evidence that could prove release. A later reconcile transaction binds the exact provider plan, approval, attempt, sanitized diagnostics, and candidate-output digests.

Provider error codes are:

| Code | Exit | Meaning |
|---|---:|---|
| AWP_PROVIDER_PLAN_INVALID | 2 | provider plan or deterministic-output contract is invalid |
| AWP_PROVIDER_APPROVAL_REQUIRED | 23 | approval-required control lacks a valid enforced approval |
| AWP_PROVIDER_APPROVAL_INVALID | 23 | approval is expired, mismatched, cross-branch, or unverifiable |
| AWP_PROVIDER_DOWNLOAD_LIMIT | 31 | compressed download exceeded its bound |
| AWP_PROVIDER_HASH_MISMATCH | 30 | complete acquired bytes do not match locked identity |
| AWP_PROVIDER_ARCHIVE_UNSAFE | 31 | archive format/member/expansion policy rejected content |
| AWP_PROVIDER_CACHE_CORRUPT | 31 | cache object is partial, polluted, wrong type, or ambiguous |
| AWP_PROVIDER_ATTEMPT_CORRUPT | 31 | attempt journal/receipt has invalid schema or transition |
| AWP_PROVIDER_CONTAINMENT_AMBIGUOUS | 31 | retry safety cannot prove the prior containment ended |
| AWP_INITIALIZER_NONDETERMINISTIC | 31 | validated candidate root differs across runs or from the locked root |
| AWP_PROVENANCE_INCOMPLETE | 30 | provenance, SPDX, full license, or notice closure is incomplete |

## 11. Test Matrix and Acceptance-Criteria Mapping

| AC | Primary provider evidence |
|---|---|
| AC-15 | provenance, full license texts, notices, lock hashes, and projected-content completeness |
| AC-28 | repeated clean-root execution and lock-bound content-root mismatch blocking |
| AC-40 | immutable-plan, finite-window approval with serialized auditable retries |
| AC-44 | one whole-file attempt object and closed prepared/released/terminal transitions |
| AC-45 | enforced direct-human approve-provider-execution branch |
| AC-49 | broker EOF/parent-death/deadline/token/receipt crash boundaries |

Required tests include:

- download truncation, wrong hash, redirect violation, archive collision, traversal, link/device, expansion limits, and quarantine;
- two cache writers and two provider attempts for one plan;
- SIGKILL before/after prepared, token send, receipt rename, acknowledgement, released update, provider exit, and terminal update;
- parent death, EOF, deadline, PID reuse, and ambiguous containment;
- changed/expired approval, task-approval cross-branch fields, model-authored approval, and insufficient capability;
- deterministic output across locale, timezone, temp path, enumeration, and repeated clean roots;
- provenance completeness and exact SPDX/full-license matching.

Task 3 consumes verified candidate output and recovery evidence. Task 6 consumes release determinism, archive safety, provenance, and license gates.

## 12. Downstream Interface Freeze

~~~json
{
  "interface_schema": "agent-workflow.feature-interface",
  "interface_version": 1,
  "producer_task": "task-2",
  "producer_feature": "providers-and-secure-cache",
  "schema_versions": {
    "agent-workflow.provider-plan": 1,
    "agent-workflow.acquisition-request": 1,
    "agent-workflow.acquisition-result": 1,
    "agent-workflow.provider-execution-result": 1,
    "agent-workflow.provider-approval": 1,
    "agent-workflow.provider-attempts": 1,
    "agent-workflow.provider-release-receipt": 1,
    "agent-workflow.initializer-output-contract": 1,
    "agent-workflow.provenance-record": 1,
    "agent-workflow.provider-failure": 1
  },
  "exports": [
    {
      "interface_id": "providers.execution.v1",
      "definition_owner": "task-2",
      "implementation_owner": "task-2",
      "schema_ids": [
        "agent-workflow.provider-plan",
        "agent-workflow.acquisition-request",
        "agent-workflow.acquisition-result",
        "agent-workflow.provider-execution-result",
        "agent-workflow.provider-approval",
        "agent-workflow.provider-attempts",
        "agent-workflow.provider-release-receipt",
        "agent-workflow.initializer-output-contract",
        "agent-workflow.provenance-record"
      ],
      "callables": [
        "acquire(AcquisitionRequest) -> AcquisitionResult | ProviderFailure",
        "execute_provider(ProviderPlan, ProviderApproval | null) -> ProviderExecutionResult | ProviderFailure"
      ],
      "consumers": ["task-3", "task-6"]
    },
    {
      "interface_id": "providers.errors.v1",
      "definition_owner": "task-2",
      "implementation_owner": "task-2",
      "schema_ids": ["agent-workflow.provider-failure"],
      "callables": [],
      "consumers": ["task-3", "task-6"]
    }
  ],
  "digest_domains": [
    "agent-workflow.provider-plan.v1",
    "agent-workflow.provider-approval.v1",
    "agent-workflow.provider-attempt.v1",
    "agent-workflow.provider-release-receipt.v1",
    "agent-workflow.initializer-content-root.v1",
    "agent-workflow.provenance-record.v1",
    "agent-workflow.feature-interface.v1"
  ],
  "error_namespace": "providers.errors.v1"
}
~~~

This approval freezes only Task 2 provider/cache contracts. It does not approve implementation code or its implementation plan.
