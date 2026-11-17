# Independent review: unattended CFX delegation

Date: 17 November 2026.

**Verdict: PASS for publication within the documented trusted-local-user,
development-only threat model.** A separate review agent independently inspected
the final changes and ran all 17 shipped installer/security tests, including the
Windows DACL check. This is an independent agent code/security review, not a
third-party certification, live FXServer/gameplay acceptance or production audit.

## Findings resolved before publication

- Concurrent scoped/full revocations used to overwrite policy changes. Revocation
  now uses atomic, monotonic markers tied to a unique grant ID.
- Server-launch permission used to follow another executable in the same workspace.
  It is now omitted without an explicitly captured complete launch target ID;
  changing executable, launch mode or managed profile invalidates that identity.
- Submission could enqueue after a completed cancellation. It now acquires the
  SQLite write lock before authorization, serializing submission with revocation.
- Malformed policy JSON did not consistently fail closed. Policy schema/root
  validation now denies it and reports an unsuccessful revocation when no valid
  grant identity can be recovered.
- Revocation during a temporarily missing server config could later revive.
  Revocation now reads protected identity separately from active authorization.
  The reviewer independently reproduced revoke/restore and confirmed it stays off.
- Private Windows secrets require more than chmod. Installation establishes an
  explicit protected owner/SYSTEM/Administrators DACL before writing secrets.

## Validation and limits

The full canonical suite passed 241 tests (240 passed, one platform skip).
The reviewer independently passed all 17 shipped installer/security tests.
An isolated final wheel test confirmed revocation while server.cfg was missing
survives restoration of that file and restarting the MCP process.

Ordinary installation remains locked; unattended delegation requires explicit
owner opt-in. Freebuff/other-host approval records are not modified. Client ACE
restrictions and foreground-only Windows input remain. The native txAdmin
mutation gate remains false: this review does not approve enabling that feature.

Local processes running as the same user and administrators remain trusted.
Already dispatched commands cannot be undone. This does not demonstrate live
server startup, resource restart, client spawn or gameplay success.

## Reviewed runtime snapshot

SHA-256 values below identify the reviewed public code before adding this report.
Shared runtime files in the two packages were checked to be byte-identical.

| Public path | SHA-256 |
| --- | --- |
| `install.py` | `20de58c0ec5268624e2435aedaea7bd6c1e91f48e7a6d51ee3e22dd0d50c0842` |
| `txadmin-integration/cfx_devkit/delegation.py` | `a392f568d45935837b6a19501c14853d598d50399dd8301f1ec73512c0895c1a` |
| `txadmin-integration/cfx_devkit/connection.py` | `58aea4fddfaaf6acec70f769408eb9b5ed236367e066b59a68bb52b07124bf64` |
| `txadmin-integration/cfx_devkit/livecontrol.py` | `74b0523d56230f1de2b881b52da0851a388faaf1ec4e7ce5a92bbe80156d4974` |
| `txadmin-integration/cfx_devkit/fxserverlaunch.py` | `aad88b98781654d3ac73665abf137b872a298ea2c1e5261fd9e8740b6bc462eb` |
| `txadmin-integration/cfx_devkit/clientlaunch.py` | `958832839038c5a1a6751cbd466ec7f05cecf9c9e1441133457e1bca81b4fd16` |
| `txadmin-integration/cfx_devkit/gameinput.py` | `1bb64ff38a9972e182178614c56ea62a5378c6094390de58b2be4fea4e135868` |
