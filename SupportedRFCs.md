# Aries AIP and RFCs Supported in Aries Cloud Agent Python

This document provides a summary of the adherence of ACA-Py to the [Aries Interop
Profiles](https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0302-aries-interop-profile),
and an overview of the ACA-Py feature set. This document is
manually updated and as such, may not be up to date with the most recent release of
ACA-Py or the repository `main` branch. Reminders (and PRs!) to update this page are
welcome! If you have any questions, please contact us on the #aries channel on
[Hyperledger Rocketchat](https://chat.hyperledger.org) or through an issue in this repo.

**Last Update**: 2021-11-12, Release 0.7.2

> The checklist version of this document was created as a joint effort
> between [Northern Block](https://northernblock.io/) and [Animo Solutions](https://animo.id/).

## AIP Support and Interoperability

See the [Aries Agent Test Harness](https://github.com/hyperledger/aries-agent-test-harness) and the
[Aries Interoperability Status](https://aries-interop.info) for daily interoperability test run results between
ACA-Py and other Aries Frameworks and Agents.

| AIP Version | Supported | Notes |
|  - | :-------: | -------- |
| AIP 1.0     | :white_check_mark:  | Fully supported. |
| AIP 2.0     | :warning:        |  Largely supported with exceptions highlighted [below](#aip-20). |

A summary of the Aries Interop Profiles and Aries RFCs supported in ACA-Py can be found [later in this document](#supported-rfcs).

## Platform Support

| Platform | Supported | Notes             |
| -------- | :-------: |  ------- |
| Server   | :white_check_mark: |    |
| Kubernetes | :white_check_mark: | BC Gov has extensive experience running ACA-Py on Red Hat's OpenShift Kubernetes Distribution. |
| Docker   | :white_check_mark: | BC Gov publishes docker images on [Docker Hub](https://hub.docker.com/r/bcgovimages/aries-cloudagent) |
| Desktop  | :warning:         | Could be run as a local service on the computer |
| iOS      | :x:        |    |
| Android  | :x:        |    |
| Browser  | :x:        |    |

## Agent Types

| Role     | Supported | Notes      |
| -------- | :-------: |  --------- |
| Issuer   | :white_check_mark:        |            |
| Holder   | :white_check_mark:        |            |
| Verifier | :white_check_mark:        |            |
| Mediator Service | :white_check_mark:        | Coming Soon: An `aries-mediator-service` repository that is a pre-configured, production ready Aries Mediator Service based on a released version of ACA-Py. |
| Mediator Client | :white_check_mark: |
| Indy Transaction Author | :white_check_mark:        |    |
| Indy Transaction Endorser | :white_check_mark:  | |

## Credential Types

| Credential Type | Supported | Notes |
| --- | :--: | -- |
| [Indy AnonCreds](https://hyperledger-indy.readthedocs.io/projects/sdk/en/latest/docs/design/002-anoncreds/README.html) | :white_check_mark: | Includes full issue VC, present proof, and revoke VC support. |
| [W3C Standard Verifiable Credentials](https://www.w3.org/TR/vc-data-model/) | :white_check_mark: | Supports only JSON-LD Credentials using the `Ed25519Signature2018`, `BbsBlsSignature2020` and `BbsBlsSignatureProof2020` signature suites.<br><br>Supports the [DIF Presentation Exchange](https://identity.foundation/presentation-exchange/) data format for presentation requests and presentation submissions. |

## DID Methods

| Method | Supported | Notes |
| --- | :--: | -- |
| `did:sov` | :white_check_mark: |  |
| `did:web` | :white_check_mark: | Resolution only |
| `did:key` | :white_check_mark: | |
| `did:peer` | :warning:| AIP 1.0-based `did:peer` DIDs are used, meaning the DIDs are not prefixed with `did:peer` and are not following the conventions of AIP 2.0's [RFC 0627: Static Peer DIDs](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0627-static-peer-dids) |

## Secure Storage Types

| Secure Storage Types | Supported | Notes |
 --- | :--: | -- |
| [Indy SDK "indy-wallet"](https://github.com/hyperledger/indy-sdk/tree/master/docs/design/003-wallet-storage) | :white_check_mark: | Full support for the features of the "indy-wallet" secure storage capabilities found in the Indy SDK. |
| [Aries Askar](https://github.com/hyperledger/aries-askar) | :warning: | Aries Askar provides equivalent/evolved secure storage and cryptography support to the "indy-wallet" part of the Indy SDK. Available in ACA-Py (activated using a startup parameters but not yet widely used. When using Askar, other Indy SDK capabilities are handled by [Indy Shared RS](https://github.com/hyperledger/indy-shared-rs) (AnonCreds) and [Indy VDR](https://github.com/hyperledger/indy-vdr) (Indy ledger interactions). |

## Miscellaneous Features

| Feature | Supported | Notes |
 --- | :--: | -- |
| Multi use invitations            | :white_check_mark:  |         |
| Invitations using public did     | :white_check_mark:        |         |
| Implicit pickup of messages in role of mediator | :white_check_mark:        |         |
| [Revocable Indy Credentials](https://github.com/hyperledger/indy-hipe/tree/main/text/0011-cred-revocation) | :white_check_mark:        |         |
| Multi-Tenancy      | :white_check_mark:        | [Documentation](https://github.com/hyperledger/aries-cloudagent-python/blob/main/Multitenancy.md) |
| Connection-less (non OOB protocol / AIP 1.0)               | :white_check_mark:        | Only for issue credential and present proof          |
| Connection-less (OOB protocol / AIP 2.0)               | :white_check_mark:        | Only for present proof          |
| Signed Attachments               | :white_check_mark:        | Used for OOB         |
| Multi ledger support (with automatic detection) | :construction:        | [Pull Request](https://github.com/hyperledger/aries-cloudagent-python/pull/1425)   |
| Persistence of mediated messages | :x:        | Messages are currently stored in an in-memory and so are subject to loss in the case of a sudden termination of an ACA-Py process. The in-memory queue is properly handled in the case of a graceful shutdown of an ACA-Py process (e.g. processing of the queue completes and no new messages are accepted). |
| Storage Import & Export           | :warning:        | Supported by directly interacting with the indy-sdk or Aries Askar (e.g., no Admin API endpoint available for wallet import & export). Aries Askar support includes the ability to import storage exported from the Indy SDK's "indy-wallet" component. |

## Supported RFCs

### AIP 1.0

All RFCs listed in [AIP 1.0](https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0302-aries-interop-profile#aries-interop-profile-version-10) are fully supported in ACA-Py. The following table
provides notes about the implementation of specific RFCs.

| RFC | Supported | Notes |
 --- | :--: | -- |
| [0025-didcomm-transports](https://github.com/hyperledger/aries-rfcs/tree/b490ebe492985e1be9804fc0763119238b2e51ab/features/0025-didcomm-transports)      | :white_check_mark:        | ACA-Py currently supports HTTP and WebSockets for both inbound and outbound messaging. Transports are pluggable and an agent instance can use multiple inbound and outbound transports.|
| [0160-connection-protocol](https://github.com/hyperledger/aries-rfcs/tree/9b0aaa39df7e8bd434126c4b33c097aae78d65bf/features/0160-connection-protocol)    | :white_check_mark:        | The agent supports Connection/DID exchange initiated from both plaintext invitations and public DIDs that enable bypassing the invitation message. |

### AIP 2.0

All RFCs listed in [AIP 2.0](https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0302-aries-interop-profile#aries-interop-profile-version-20) (including the sub-targets) 
are fully supported in ACA-Py **EXCEPT** as noted in the table below.

| RFC | Supported | Notes |
 --- | :--: | -- |
| [0023-did-exchange](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0023-did-exchange)   | :warning:   |     Not using DIDDoc conventions yet, still using DID format of 0160-connections (which is incorrect and outdated). Also using incorrect format for `did:peer`  (or not using a `did:` prefix at all) |
| [0183-revocation-notification](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0183-revocation-notification)  | :construction:      |  [PR is in review](https://github.com/hyperledger/aries-cloudagent-python/pull/1464) |
| [0211-route-coordination](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0211-route-coordination)   | :warning:        | Only pre-AIP 2.0 version. Must be updated to use `did:key` for full AIP 2.0 support  |
| [0317-please-ack](https://github.com/hyperledger/aries-rfcs/tree/main/features/0317-please-ack) |  :x: | |
| [0360-use-did-key](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0360-use-did-key)     | :warning:  |  Creating and resolving `did:key` DIDs is supported, but not all protocols are updated yet to use `did:key`. This is a breaking change for AIP 1.0 -> AIP 2.0.                |
| [0519-goal-codes](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/concepts/0519-goal-codes) | :x: | To be implemented as part of the work on RFC 0557 Discover Features V2 (below) |
| [0557-discover-features-v2](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0557-discover-features-v2)  | :x:        | [Issue exists](https://github.com/hyperledger/aries-cloudagent-python/issues/1466) and is being implemented.  |
| [0587-encryption-envelope-v2](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0587-encryption-envelope-v2) | :construction: | Support for the DIDComm V2 envelope format is a work in progress, including the PRs ([AIP-2 base64url consistency](https://github.com/hyperledger/aries-cloudagent-python/pull/1188) and [Small AIP-2 updates](https://github.com/hyperledger/aries-cloudagent-python/pull/1056)) |
| [0627-static-peer-dids](https://github.com/hyperledger/aries-rfcs/tree/b3a3942ef052039e73cd23d847f42947f8287da2/features/0627-static-peer-dids)          | :x:  |  |

### Other Supported RFCs

| RFC | Supported | Notes |
| --- | :--: | -- |
| [0031-discover-features](https://github.com/hyperledger/aries-rfcs/blob/main/features/0031-discover-features/README.md)           | :warning:        | Rarely (never?) used, and in implementing the V2 version of the protocol, the V1 version was found to be incomplete. It will be updated as part of the V2 work.  |
| [0028-introduce](https://github.com/hyperledger/aries-rfcs/blob/main/features/0028-introduce/README.md)            | :white_check_mark:        |      |
| [00509-action-menu](https://github.com/hyperledger/aries-rfcs/blob/main/features/0509-action-menu/README.md)       | :white_check_mark:        |      |
