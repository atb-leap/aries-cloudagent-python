"""Classes to manage connections."""

import asyncio
import json
import logging

from typing import Mapping, Sequence, Optional

from ....connections.base_manager import BaseConnectionManager
from ....connections.models.conn_record import ConnRecord
from ....connections.util import mediation_record_if_id
from ....core.error import BaseError
from ....core.profile import Profile
from ....did.did_key import DIDKey
from ....indy.holder import IndyHolder
from ....indy.models.xform import indy_proof_req_preview2indy_requested_creds
from ....messaging.decorators.attach_decorator import AttachDecorator
from ....messaging.responder import BaseResponder
from ....multitenant.base import BaseMultitenantManager
from ....storage.error import StorageNotFoundError
from ....transport.inbound.receipt import MessageReceipt
from ....wallet.base import BaseWallet
from ....wallet.util import b64_to_bytes
from ....wallet.key_type import KeyType

from ...coordinate_mediation.v1_0.manager import MediationManager
from ...connections.v1_0.manager import ConnectionManager
from ...connections.v1_0.messages.connection_invitation import ConnectionInvitation
from ...didcomm_prefix import DIDCommPrefix
from ...didexchange.v1_0.manager import DIDXManager
from ...issue_credential.v1_0.manager import CredentialManager as V10CredManager
from ...issue_credential.v1_0.messages.credential_offer import (
    CredentialOffer as V10CredOffer,
)
from ...issue_credential.v1_0.message_types import CREDENTIAL_OFFER
from ...issue_credential.v1_0.models.credential_exchange import V10CredentialExchange
from ...issue_credential.v2_0.manager import V20CredManager
from ...issue_credential.v2_0.messages.cred_offer import V20CredOffer
from ...issue_credential.v2_0.message_types import CRED_20_OFFER
from ...issue_credential.v2_0.models.cred_ex_record import V20CredExRecord
from ...present_proof.v1_0.manager import PresentationManager
from ...present_proof.v1_0.message_types import PRESENTATION_REQUEST
from ...present_proof.v1_0.models.presentation_exchange import V10PresentationExchange
from ...present_proof.v2_0.manager import V20PresManager
from ...present_proof.v2_0.message_types import PRES_20_REQUEST
from ...present_proof.v2_0.models.pres_exchange import V20PresExRecord

from .messages.invitation import HSProto, InvitationMessage
from .messages.problem_report import OOBProblemReport
from .messages.reuse import HandshakeReuse
from .messages.reuse_accept import HandshakeReuseAccept
from .messages.service import Service as ServiceMessage
from .models.invitation import InvitationRecord

LOGGER = logging.getLogger(__name__)


class OutOfBandManagerError(BaseError):
    """Out of band error."""


class OutOfBandManagerNotImplementedError(BaseError):
    """Out of band error for unimplemented functionality."""


class OutOfBandManager(BaseConnectionManager):
    """Class for managing out of band messages."""

    def __init__(self, profile: Profile):
        """
        Initialize a OutOfBandManager.

        Args:
            profile: The profile for this out of band manager
        """
        self._profile = profile
        super().__init__(self._profile)

    @property
    def profile(self) -> Profile:
        """
        Accessor for the current profile.

        Returns:
            The profile for this connection manager

        """
        return self._profile

    async def create_invitation(
        self,
        my_label: str = None,
        my_endpoint: str = None,
        auto_accept: bool = None,
        public: bool = False,
        hs_protos: Sequence[HSProto] = None,
        multi_use: bool = False,
        alias: str = None,
        attachments: Sequence[Mapping] = None,
        metadata: dict = None,
        mediation_id: str = None,
    ) -> InvitationRecord:
        """
        Generate new connection invitation.

        This interaction represents an out-of-band communication channel. In the future
        and in practice, these sort of invitations will be received over any number of
        channels such as SMS, Email, QR Code, NFC, etc.

        Args:
            my_label: label for this connection
            my_endpoint: endpoint where other party can reach me
            auto_accept: auto-accept a corresponding connection request
                (None to use config)
            public: set to create an invitation from the public DID
            hs_protos: list of handshake protocols to include
            multi_use: set to True to create an invitation for multiple-use connection
            alias: optional alias to apply to connection for later use
            attachments: list of dicts in form of {"id": ..., "type": ...}

        Returns:
            Invitation record

        """
        mediation_mgr = MediationManager(self.profile)
        mediation_record = await mediation_record_if_id(
            self.profile,
            mediation_id,
            or_default=True,
        )
        keylist_updates = None

        if not (hs_protos or attachments):
            raise OutOfBandManagerError(
                "Invitation must include handshake protocols, "
                "request attachments, or both"
            )

        # Multitenancy setup
        multitenant_mgr = self.profile.inject_or(BaseMultitenantManager)
        wallet_id = self.profile.settings.get("wallet.id")

        accept = bool(
            auto_accept
            or (
                auto_accept is None
                and self.profile.settings.get("debug.auto_accept_requests")
            )
        )
        if public:
            if multi_use:
                raise OutOfBandManagerError(
                    "Cannot create public invitation with multi_use"
                )
            if metadata:
                raise OutOfBandManagerError(
                    "Cannot store metadata on public invitations"
                )

        message_attachments = []
        for atch in attachments or []:
            a_type = atch.get("type")
            a_id = atch.get("id")

            if a_type == "credential-offer":
                try:
                    async with self.profile.session() as session:
                        cred_ex_rec = await V10CredentialExchange.retrieve_by_id(
                            session,
                            a_id,
                        )
                    message_attachments.append(
                        InvitationMessage.wrap_message(
                            cred_ex_rec.credential_offer_dict.serialize()
                        )
                    )
                except StorageNotFoundError:
                    async with self.profile.session() as session:
                        cred_ex_rec = await V20CredExRecord.retrieve_by_id(
                            session,
                            a_id,
                        )
                    message_attachments.append(
                        InvitationMessage.wrap_message(
                            cred_ex_rec.cred_offer.serialize()
                        )
                    )
            elif a_type == "present-proof":
                try:
                    async with self.profile.session() as session:
                        pres_ex_rec = await V10PresentationExchange.retrieve_by_id(
                            session,
                            a_id,
                        )
                    message_attachments.append(
                        InvitationMessage.wrap_message(
                            pres_ex_rec.presentation_request_dict.serialize()
                        )
                    )
                except StorageNotFoundError:
                    async with self.profile.session() as session:
                        pres_ex_rec = await V20PresExRecord.retrieve_by_id(
                            session,
                            a_id,
                        )
                    message_attachments.append(
                        InvitationMessage.wrap_message(
                            pres_ex_rec.pres_request.serialize()
                        )
                    )
            else:
                raise OutOfBandManagerError(f"Unknown attachment type: {a_type}")

        handshake_protocols = [
            DIDCommPrefix.qualify_current(hsp.name) for hsp in hs_protos or []
        ] or None
        connection_protocol = (
            hs_protos[0].name if hs_protos and len(hs_protos) >= 1 else None
        )

        if public:
            if not self.profile.settings.get("public_invites"):
                raise OutOfBandManagerError("Public invitations are not enabled")

            async with self.profile.session() as session:
                wallet = session.inject(BaseWallet)
                public_did = await wallet.get_public_did()
            if not public_did:
                raise OutOfBandManagerError(
                    "Cannot create public invitation with no public DID"
                )

            invi_msg = InvitationMessage(  # create invitation message
                label=my_label or self.profile.settings.get("default_label"),
                handshake_protocols=handshake_protocols,
                requests_attach=message_attachments,
                services=[f"did:sov:{public_did.did}"],
            )
            keylist_updates = await mediation_mgr.add_key(
                public_did.verkey, keylist_updates
            )

            endpoint, *_ = await self.resolve_invitation(public_did.did)
            invi_url = invi_msg.to_url(endpoint)

            conn_rec = ConnRecord(  # create connection record
                invitation_key=public_did.verkey,
                invitation_msg_id=invi_msg._id,
                their_role=ConnRecord.Role.REQUESTER.rfc23,
                state=ConnRecord.State.INVITATION.rfc23,
                accept=ConnRecord.ACCEPT_AUTO if accept else ConnRecord.ACCEPT_MANUAL,
                alias=alias,
                connection_protocol=connection_protocol,
            )

            async with self.profile.session() as session:
                await conn_rec.save(session, reason="Created new invitation")
                await conn_rec.attach_invitation(session, invi_msg)

            if multitenant_mgr and wallet_id:  # add mapping for multitenant relay
                await multitenant_mgr.add_key(
                    wallet_id, public_did.verkey, skip_if_exists=True
                )

        else:
            invitation_mode = (
                ConnRecord.INVITATION_MODE_MULTI
                if multi_use
                else ConnRecord.INVITATION_MODE_ONCE
            )

            if not my_endpoint:
                my_endpoint = self.profile.settings.get("default_endpoint")

            # Create and store new invitation key

            async with self.profile.session() as session:
                wallet = session.inject(BaseWallet)
                connection_key = await wallet.create_signing_key(KeyType.ED25519)
            keylist_updates = await mediation_mgr.add_key(
                connection_key.verkey, keylist_updates
            )
            # Add mapping for multitenant relay
            if multitenant_mgr and wallet_id:
                await multitenant_mgr.add_key(wallet_id, connection_key.verkey)
            # Initializing  InvitationMessage here to include
            # invitation_msg_id in webhook poyload
            invi_msg = InvitationMessage()
            # Create connection record
            conn_rec = ConnRecord(
                invitation_key=connection_key.verkey,
                their_role=ConnRecord.Role.REQUESTER.rfc23,
                state=ConnRecord.State.INVITATION.rfc23,
                accept=ConnRecord.ACCEPT_AUTO if accept else ConnRecord.ACCEPT_MANUAL,
                invitation_mode=invitation_mode,
                alias=alias,
                connection_protocol=connection_protocol,
                invitation_msg_id=invi_msg._id,
            )

            async with self.profile.session() as session:
                await conn_rec.save(session, reason="Created new connection")

            routing_keys = []
            # The base wallet can act as a mediator for all tenants
            if multitenant_mgr and wallet_id:
                base_mediation_record = await multitenant_mgr.get_default_mediator()

                if base_mediation_record:
                    routing_keys = base_mediation_record.routing_keys
                    my_endpoint = base_mediation_record.endpoint

                    # If we use a mediator for the base wallet we don't
                    # need to register the key at the subwallet mediator
                    # because it only needs to know the key of the base mediator
                    # sub wallet mediator -> base wallet mediator -> agent
                    keylist_updates = None
            if mediation_record:
                routing_keys = [*routing_keys, *mediation_record.routing_keys]
                my_endpoint = mediation_record.endpoint

                # Save that this invitation was created with mediation

                async with self.profile.session() as session:
                    await conn_rec.metadata_set(
                        session, "mediation", {"id": mediation_record.mediation_id}
                    )

                if keylist_updates:
                    responder = self.profile.inject_or(BaseResponder)
                    await responder.send(
                        keylist_updates, connection_id=mediation_record.connection_id
                    )
            routing_keys = [
                key
                if len(key.split(":")) == 3
                else DIDKey.from_public_key_b58(key, KeyType.ED25519).did
                for key in routing_keys
            ]
            # Create connection invitation message
            # Note: Need to split this into two stages to support inbound routing
            # of invitations
            # Would want to reuse create_did_document and convert the result
            invi_msg.label = my_label or self.profile.settings.get("default_label")
            invi_msg.handshake_protocols = handshake_protocols
            invi_msg.requests_attach = message_attachments
            invi_msg.services = [
                ServiceMessage(
                    _id="#inline",
                    _type="did-communication",
                    recipient_keys=[
                        DIDKey.from_public_key_b58(
                            connection_key.verkey, KeyType.ED25519
                        ).did
                    ],
                    service_endpoint=my_endpoint,
                    routing_keys=routing_keys,
                )
            ]
            invi_url = invi_msg.to_url()

            # Update connection record

            async with self.profile.session() as session:
                await conn_rec.attach_invitation(session, invi_msg)

            if metadata:
                async with self.profile.session() as session:
                    for key, value in metadata.items():
                        await conn_rec.metadata_set(session, key, value)

        return InvitationRecord(  # for return via admin API, not storage
            state=InvitationRecord.STATE_INITIAL,
            invi_msg_id=invi_msg._id,
            invitation=invi_msg,
            invitation_url=invi_url,
        )

    async def receive_invitation(
        self,
        invitation: InvitationMessage,
        use_existing_connection: bool = True,
        auto_accept: bool = None,
        alias: str = None,
        mediation_id: str = None,
    ) -> ConnRecord:
        """
        Receive an out of band invitation message.

        Args:
            invitation: invitation message
            use_existing_connection: whether to use existing connection if possible
            auto_accept: whether to accept the invitation automatically
            alias: Alias for connection record
            mediation_id: mediation identifier

        Returns:
            ConnRecord, serialized

        """
        if mediation_id:
            try:
                await mediation_record_if_id(self.profile, mediation_id)
            except StorageNotFoundError:
                mediation_id = None

        # There must be exactly 1 service entry
        if len(invitation.services) != 1:
            raise OutOfBandManagerError("service array must have exactly one element")

        if not (invitation.requests_attach or invitation.handshake_protocols):
            raise OutOfBandManagerError(
                "Invitation must specify handshake_protocols, requests_attach, or both"
            )
        # Get the single service item
        oob_service_item = invitation.services[0]
        if isinstance(oob_service_item, ServiceMessage):
            service = oob_service_item
            public_did = None
        else:
            # If it's in the did format, we need to convert to a full service block
            # An existing connection can only be reused based on a public DID
            # in an out-of-band message (RFC 0434).

            service_did = oob_service_item

            # TODO: resolve_invitation should resolve key_info objects
            # or something else that includes the key type. We now assume
            # ED25519 keys
            endpoint, recipient_keys, routing_keys = await self.resolve_invitation(
                service_did
            )
            public_did = service_did.split(":")[-1]
            service = ServiceMessage.deserialize(
                {
                    "id": "#inline",
                    "type": "did-communication",
                    "recipientKeys": [
                        DIDKey.from_public_key_b58(key, KeyType.ED25519).did
                        for key in recipient_keys
                    ],
                    "routingKeys": [
                        DIDKey.from_public_key_b58(key, KeyType.ED25519).did
                        for key in routing_keys
                    ],
                    "serviceEndpoint": endpoint,
                }
            )

        unq_handshake_protos = [
            HSProto.get(hsp)
            for hsp in dict.fromkeys(
                [
                    DIDCommPrefix.unqualify(proto)
                    for proto in invitation.handshake_protocols
                ]
            )
        ]

        # Reuse Connection - only if started by an invitation with Public DID
        conn_rec = None
        if public_did is not None:  # invite has public DID: seek existing connection
            tag_filter = {}
            post_filter = {}
            # post_filter["state"] = ConnRecord.State.COMPLETED.rfc160
            post_filter["their_public_did"] = public_did
            conn_rec = await self.find_existing_connection(
                tag_filter=tag_filter, post_filter=post_filter
            )
        if conn_rec is not None:
            num_included_protocols = len(unq_handshake_protos)
            num_included_req_attachments = len(invitation.requests_attach)
            # With handshake protocol, request attachment; use existing connection
            if (
                num_included_protocols >= 1
                and num_included_req_attachments == 0
                and use_existing_connection
            ):
                await self.create_handshake_reuse_message(
                    invi_msg=invitation,
                    conn_record=conn_rec,
                )
                try:
                    await asyncio.wait_for(
                        self.check_reuse_msg_state(
                            conn_rec=conn_rec,
                        ),
                        15,
                    )
                    async with self.profile.session() as session:
                        await conn_rec.metadata_delete(
                            session=session, key="reuse_msg_id"
                        )

                        msg_state = await conn_rec.metadata_get(
                            session, "reuse_msg_state"
                        )

                    if msg_state == "not_accepted":
                        conn_rec = None
                    else:
                        async with self.profile.session() as session:
                            await conn_rec.metadata_delete(
                                session=session, key="reuse_msg_state"
                            )
                except asyncio.TimeoutError:
                    # If no reuse_accepted or problem_report message was received within
                    # the 15s timeout then a new connection to be created
                    async with self.profile.session() as session:
                        await conn_rec.metadata_delete(
                            session=session, key="reuse_msg_id"
                        )
                        await conn_rec.metadata_delete(
                            session=session, key="reuse_msg_state"
                        )
                        conn_rec.state = ConnRecord.State.ABANDONED.rfc160
                        await conn_rec.save(session, reason="Sent connection request")
                    conn_rec = None
            # Inverse of the following cases
            # Handshake_Protocol not included
            # Request_Attachment included
            # Use_Existing_Connection Yes
            # Handshake_Protocol included
            # Request_Attachment included
            # Use_Existing_Connection Yes
            elif not (
                (
                    num_included_protocols == 0
                    and num_included_req_attachments >= 1
                    and use_existing_connection
                )
                or (
                    num_included_protocols >= 1
                    and num_included_req_attachments >= 1
                    and use_existing_connection
                )
            ):
                conn_rec = None
        if conn_rec is None:
            if not unq_handshake_protos:
                raise OutOfBandManagerError(
                    "No existing connection exists and handshake_protocol is missing"
                )
            # Create a new connection
            for proto in unq_handshake_protos:
                if proto is HSProto.RFC23:
                    didx_mgr = DIDXManager(self.profile)
                    conn_rec = await didx_mgr.receive_invitation(
                        invitation=invitation,
                        their_public_did=public_did,
                        auto_accept=auto_accept,
                        alias=alias,
                        mediation_id=mediation_id,
                    )
                elif proto is HSProto.RFC160:
                    service.recipient_keys = [
                        DIDKey.from_did(key).public_key_b58
                        for key in service.recipient_keys or []
                    ]
                    service.routing_keys = [
                        DIDKey.from_did(key).public_key_b58
                        for key in service.routing_keys
                    ] or []
                    connection_invitation = ConnectionInvitation.deserialize(
                        {
                            "@id": invitation._id,
                            "@type": DIDCommPrefix.qualify_current(proto.name),
                            "label": invitation.label,
                            "recipientKeys": service.recipient_keys,
                            "serviceEndpoint": service.service_endpoint,
                            "routingKeys": service.routing_keys,
                        }
                    )
                    conn_mgr = ConnectionManager(self.profile)
                    conn_rec = await conn_mgr.receive_invitation(
                        invitation=connection_invitation,
                        their_public_did=public_did,
                        auto_accept=auto_accept,
                        alias=alias,
                        mediation_id=mediation_id,
                    )
                if conn_rec is not None:
                    break

        # Request Attach
        if len(invitation.requests_attach) >= 1 and conn_rec is not None:
            req_attach = invitation.requests_attach[0]
            if isinstance(req_attach, AttachDecorator):
                if req_attach.data is not None:
                    unq_req_attach_type = DIDCommPrefix.unqualify(
                        req_attach.content["@type"]
                    )
                    if unq_req_attach_type == PRESENTATION_REQUEST:
                        await self._process_pres_request_v1(
                            req_attach=req_attach,
                            service=service,
                            conn_rec=conn_rec,
                            trace=(invitation._trace is not None),
                        )
                    elif unq_req_attach_type == PRES_20_REQUEST:
                        await self._process_pres_request_v2(
                            req_attach=req_attach,
                            service=service,
                            conn_rec=conn_rec,
                            trace=(invitation._trace is not None),
                        )
                    elif unq_req_attach_type == CREDENTIAL_OFFER:
                        if auto_accept or self.profile.settings.get(
                            "debug.auto_accept_invites"
                        ):
                            try:
                                conn_rec = await asyncio.wait_for(
                                    self.conn_rec_is_active(conn_rec.connection_id),
                                    7,
                                )
                            except asyncio.TimeoutError:
                                LOGGER.warning(
                                    "Connection not ready to receive credential, "
                                    f"For connection_id:{conn_rec.connection_id} and "
                                    f"invitation_msg_id {invitation._id}",
                                )
                        await self._process_cred_offer_v1(
                            req_attach=req_attach,
                            conn_rec=conn_rec,
                            trace=(invitation._trace is not None),
                        )
                    elif unq_req_attach_type == CRED_20_OFFER:
                        if auto_accept or self.profile.settings.get(
                            "debug.auto_accept_invites"
                        ):
                            try:
                                conn_rec = await asyncio.wait_for(
                                    self.conn_rec_is_active(conn_rec.connection_id),
                                    7,
                                )
                            except asyncio.TimeoutError:
                                LOGGER.warning(
                                    "Connection not ready to receive credential, "
                                    f"For connection_id:{conn_rec.connection_id} and "
                                    f"invitation_msg_id {invitation._id}",
                                )
                        await self._process_cred_offer_v2(
                            req_attach=req_attach,
                            conn_rec=conn_rec,
                            trace=(invitation._trace is not None),
                        )
                    else:
                        raise OutOfBandManagerError(
                            (
                                "Unsupported requests~attach type "
                                f"{req_attach.content['@type']}: must unqualify to"
                                f"{PRESENTATION_REQUEST} or {PRES_20_REQUEST}"
                                f"{CREDENTIAL_OFFER} or {CRED_20_OFFER}"
                            )
                        )
            else:
                raise OutOfBandManagerError("requests~attach is not properly formatted")

        return conn_rec

    async def _process_pres_request_v1(
        self,
        req_attach: AttachDecorator,
        service: ServiceMessage,
        conn_rec: ConnRecord,
        trace: bool,
    ):
        """
        Create exchange for v1 pres request attachment, auto-present if configured.

        Args:
            req_attach: request attachment on invitation
            service: service message from invitation
            conn_rec: connection record
            trace: trace setting for presentation exchange record
        """
        pres_mgr = PresentationManager(self.profile)
        pres_request_msg = req_attach.content
        indy_proof_request = json.loads(
            b64_to_bytes(
                pres_request_msg["request_presentations~attach"][0]["data"]["base64"]
            )
        )
        oob_invi_service = service.serialize()
        pres_request_msg["~service"] = {
            "recipientKeys": oob_invi_service.get("recipientKeys"),
            "routingKeys": oob_invi_service.get("routingKeys"),
            "serviceEndpoint": oob_invi_service.get("serviceEndpoint"),
        }
        pres_ex_record = V10PresentationExchange(
            connection_id=conn_rec.connection_id,
            thread_id=pres_request_msg["@id"],
            initiator=V10PresentationExchange.INITIATOR_EXTERNAL,
            role=V10PresentationExchange.ROLE_PROVER,
            presentation_request=indy_proof_request,
            presentation_request_dict=pres_request_msg,
            auto_present=self.profile.context.settings.get(
                "debug.auto_respond_presentation_request"
            ),
            trace=trace,
        )

        pres_ex_record = await pres_mgr.receive_request(pres_ex_record)
        if pres_ex_record.auto_present:
            try:
                async with self.profile.session() as session:
                    req_creds = await indy_proof_req_preview2indy_requested_creds(
                        indy_proof_req=indy_proof_request,
                        preview=None,
                        holder=session.inject(IndyHolder),
                    )
            except ValueError as err:
                LOGGER.exception(
                    "Unable to auto-respond to presentation request "
                    f"{pres_ex_record.presentation_exchange_id}, prover"
                    "  could still build proof manually"
                )
                raise OutOfBandManagerError(
                    "Cannot auto-respond to presentation request attachment"
                ) from err

            (pres_ex_record, presentation_message) = await pres_mgr.create_presentation(
                presentation_exchange_record=pres_ex_record,
                requested_credentials=req_creds,
                comment=(
                    "auto-presented for proof request nonce={}".format(
                        indy_proof_request["nonce"]
                    )
                ),
            )
            responder = self.profile.inject_or(BaseResponder)
            if responder:
                await responder.send(
                    message=presentation_message,
                    target_list=await self.fetch_connection_targets(
                        connection=conn_rec
                    ),
                )
        else:
            raise OutOfBandManagerError(
                (
                    "Configuration sets auto_present false: cannot "
                    "respond automatically to presentation requests"
                )
            )

    async def _process_pres_request_v2(
        self,
        req_attach: AttachDecorator,
        service: ServiceMessage,
        conn_rec: ConnRecord,
        trace: bool,
    ):
        """
        Create exchange for v2 pres request attachment, auto-present if configured.

        Args:
            req_attach: request attachment on invitation
            service: service message from invitation
            conn_rec: connection record
            trace: trace setting for presentation exchange record
        """
        pres_mgr = V20PresManager(self.profile)
        pres_request_msg = req_attach.content
        oob_invi_service = service.serialize()
        pres_request_msg["~service"] = {
            "recipientKeys": oob_invi_service.get("recipientKeys"),
            "routingKeys": oob_invi_service.get("routingKeys"),
            "serviceEndpoint": oob_invi_service.get("serviceEndpoint"),
        }
        pres_ex_record = V20PresExRecord(
            connection_id=conn_rec.connection_id,
            thread_id=pres_request_msg["@id"],
            initiator=V20PresExRecord.INITIATOR_EXTERNAL,
            role=V20PresExRecord.ROLE_PROVER,
            pres_request=pres_request_msg,
            auto_present=self.profile.context.settings.get(
                "debug.auto_respond_presentation_request"
            ),
            trace=trace,
        )

        pres_ex_record = await pres_mgr.receive_pres_request(pres_ex_record)
        if pres_ex_record.auto_present:
            (pres_ex_record, pres_msg) = await pres_mgr.create_pres(
                pres_ex_record=pres_ex_record,
                comment=(
                    f"auto-presented for proof requests"
                    f", pres_ex_record: {pres_ex_record.pres_ex_id}"
                ),
            )
            responder = self.profile.inject_or(BaseResponder)
            if responder:
                await responder.send(
                    message=pres_msg,
                    target_list=await self.fetch_connection_targets(
                        connection=conn_rec
                    ),
                )
        else:
            raise OutOfBandManagerError(
                (
                    "Configuration set auto_present false: cannot "
                    "respond automatically to presentation requests"
                )
            )

    async def _process_cred_offer_v1(
        self,
        req_attach: AttachDecorator,
        conn_rec: ConnRecord,
        trace: bool,
    ):
        """
        Create exchange for v1 cred offer attachment, auto-offer if configured.

        Args:
            req_attach: request attachment on invitation
            service: service message from invitation
            conn_rec: connection record
        """
        cred_mgr = V10CredManager(self.profile)
        cred_offer_msg = req_attach.content
        cred_offer = V10CredOffer.deserialize(cred_offer_msg)
        cred_offer.assign_trace_decorator(self.profile.settings, trace)
        # receive credential offer
        cred_ex_record = await cred_mgr.receive_offer(
            message=cred_offer, connection_id=conn_rec.connection_id
        )
        if self.profile.context.settings.get("debug.auto_respond_credential_offer"):
            if conn_rec.is_ready:
                (_, cred_request_message) = await cred_mgr.create_request(
                    cred_ex_record=cred_ex_record,
                    holder_did=conn_rec.my_did,
                )
                responder = self.profile.inject_or(BaseResponder)
                if responder:
                    await responder.send(
                        message=cred_request_message,
                        target_list=await self.fetch_connection_targets(
                            connection=conn_rec
                        ),
                    )
        else:
            raise OutOfBandManagerError(
                (
                    "Configuration sets auto_offer false: cannot "
                    "respond automatically to credential offers"
                )
            )

    async def _process_cred_offer_v2(
        self,
        req_attach: AttachDecorator,
        conn_rec: ConnRecord,
        trace: bool,
    ):
        """
        Create exchange for v1 cred offer attachment, auto-offer if configured.

        Args:
            req_attach: request attachment on invitation
            service: service message from invitation
            conn_rec: connection record
        """
        cred_mgr = V20CredManager(self.profile)
        cred_offer_msg = req_attach.content
        cred_offer = V20CredOffer.deserialize(cred_offer_msg)
        cred_offer.assign_trace_decorator(self.profile.settings, trace)

        cred_ex_record = await cred_mgr.receive_offer(
            cred_offer_message=cred_offer, connection_id=conn_rec.connection_id
        )
        if self.profile.context.settings.get("debug.auto_respond_credential_offer"):
            if conn_rec.is_ready:
                (_, cred_request_message) = await cred_mgr.create_request(
                    cred_ex_record=cred_ex_record,
                    holder_did=conn_rec.my_did,
                )
                responder = self.profile.inject_or(BaseResponder)
                if responder:
                    await responder.send(
                        message=cred_request_message,
                        target_list=await self.fetch_connection_targets(
                            connection=conn_rec
                        ),
                    )
        else:
            raise OutOfBandManagerError(
                (
                    "Configuration sets auto_offer false: cannot "
                    "respond automatically to credential offers"
                )
            )

    async def find_existing_connection(
        self,
        tag_filter: dict,
        post_filter: dict,
    ) -> Optional[ConnRecord]:
        """
        Find existing ConnRecord.

        Args:
            tag_filter: The filter dictionary to apply
            post_filter: Additional value filters to apply matching positively,
                with sequence values specifying alternatives to match (hit any)

        Returns:
            ConnRecord or None

        """
        async with self.profile.session() as session:
            conn_records = await ConnRecord.query(
                session,
                tag_filter=tag_filter,
                post_filter_positive=post_filter,
                alt=True,
            )
        if not conn_records:
            return None
        else:
            for conn_rec in conn_records:
                if conn_rec.state == "active":
                    return conn_rec
            return None

    async def check_reuse_msg_state(
        self,
        conn_rec: ConnRecord,
    ):
        """
        Check reuse message state from the ConnRecord Metadata.

        Args:
            conn_rec: The required ConnRecord with updated metadata

        Returns:

        """
        received = False
        while not received:
            msg_state = None
            async with self.profile.session() as session:
                msg_state = await conn_rec.metadata_get(session, "reuse_msg_state")
            if msg_state != "initial":
                received = True
        return

    async def conn_rec_is_active(self, conn_rec_id: str) -> ConnRecord:
        """
        Return when ConnRecord state becomes active.

        Args:
            conn_rec: ConnRecord

        Returns:
            ConnRecord

        """
        while True:
            async with self.profile.session() as session:
                conn_rec = await ConnRecord.retrieve_by_id(session, conn_rec_id)
                if conn_rec.is_ready:
                    return conn_rec
            asyncio.sleep(0.5)

    async def create_handshake_reuse_message(
        self,
        invi_msg: InvitationMessage,
        conn_record: ConnRecord,
    ) -> None:
        """
        Create and Send a Handshake Reuse message under RFC 0434.

        Args:
            invi_msg: OOB Invitation Message
            service: Service block extracted from the OOB invitation

        Returns:

        Raises:
            OutOfBandManagerError: If there is an issue creating or
            sending the OOB invitation

        """
        try:
            # ID of Out-of-Band invitation to use as a pthid
            # pthid = invi_msg._id
            pthid = conn_record.invitation_msg_id
            reuse_msg = HandshakeReuse()
            thid = reuse_msg._id
            reuse_msg.assign_thread_id(thid=thid, pthid=pthid)
            connection_targets = await self.fetch_connection_targets(
                connection=conn_record
            )
            responder = self.profile.inject_or(BaseResponder)
            if responder:
                await responder.send(
                    message=reuse_msg,
                    target_list=connection_targets,
                )
                async with self.profile.session() as session:
                    await conn_record.metadata_set(
                        session=session, key="reuse_msg_id", value=reuse_msg._id
                    )
                    await conn_record.metadata_set(
                        session=session, key="reuse_msg_state", value="initial"
                    )
        except Exception as err:
            raise OutOfBandManagerError(
                f"Error on creating and sending a handshake reuse message: {err}"
            )

    async def receive_reuse_message(
        self,
        reuse_msg: HandshakeReuse,
        receipt: MessageReceipt,
    ) -> None:
        """
        Receive and process a HandshakeReuse message under RFC 0434.

        Process a `HandshakeReuse` message by looking up
        the connection records using the MessageReceipt sender DID.

        Args:
            reuse_msg: The `HandshakeReuse` to process
            receipt: The message receipt

        Returns:

        Raises:
            OutOfBandManagerError: If the existing connection is not active
            or the connection does not exists

        """
        try:
            invi_msg_id = reuse_msg._thread.pthid
            reuse_msg_id = reuse_msg._thread.thid
            tag_filter = {}
            post_filter = {}
            # post_filter["state"] = "active"
            # tag_filter["their_did"] = receipt.sender_did
            post_filter["invitation_msg_id"] = invi_msg_id
            conn_record = await self.find_existing_connection(
                tag_filter=tag_filter, post_filter=post_filter
            )
            responder = self.profile.inject_or(BaseResponder)
            if conn_record is not None:
                # For ConnRecords created using did-exchange
                reuse_accept_msg = HandshakeReuseAccept()
                reuse_accept_msg.assign_thread_id(thid=reuse_msg_id, pthid=invi_msg_id)
                connection_targets = await self.fetch_connection_targets(
                    connection=conn_record
                )
                if responder:
                    await responder.send(
                        message=reuse_accept_msg,
                        target_list=connection_targets,
                    )
                # This is not required as now we attaching the invitation_msg_id
                # using original invitation [from existing connection]
                #
                # Delete the ConnRecord created; re-use existing connection
                # invi_id_post_filter = {}
                # invi_id_post_filter["invitation_msg_id"] = invi_msg_id
                # conn_rec_to_delete = await self.find_existing_connection(
                #     tag_filter={},
                #     post_filter=invi_id_post_filter,
                # )
                # if conn_rec_to_delete is not None:
                #     if conn_record.connection_id != conn_rec_to_delete.connection_id:
                #         await conn_rec_to_delete.delete_record(session=self._session)
            else:
                conn_record = await self.find_existing_connection(
                    tag_filter={"their_did": receipt.sender_did}, post_filter={}
                )
                # Problem Report is redundant in this case as with no active
                # connection, it cannot reach the invitee any way
                if conn_record is not None:
                    # For ConnRecords created using RFC 0160 connections
                    reuse_accept_msg = HandshakeReuseAccept()
                    reuse_accept_msg.assign_thread_id(
                        thid=reuse_msg_id, pthid=invi_msg_id
                    )
                    connection_targets = await self.fetch_connection_targets(
                        connection=conn_record
                    )
                    if responder:
                        await responder.send(
                            message=reuse_accept_msg,
                            target_list=connection_targets,
                        )
        except StorageNotFoundError:
            raise OutOfBandManagerError(
                (f"No existing ConnRecord found for OOB Invitee, {receipt.sender_did}"),
            )

    async def receive_reuse_accepted_message(
        self,
        reuse_accepted_msg: HandshakeReuseAccept,
        receipt: MessageReceipt,
        conn_record: ConnRecord,
    ) -> None:
        """
        Receive and process a HandshakeReuseAccept message under RFC 0434.

        Process a `HandshakeReuseAccept` message by updating the ConnRecord metadata
        state to `accepted`.

        Args:
            reuse_accepted_msg: The `HandshakeReuseAccept` to process
            receipt: The message receipt

        Returns:

        Raises:
            OutOfBandManagerError: if there is an error in processing the
            HandshakeReuseAccept message

        """
        try:
            invi_msg_id = reuse_accepted_msg._thread.pthid
            thread_reuse_msg_id = reuse_accepted_msg._thread.thid
            async with self.profile.session() as session:
                conn_reuse_msg_id = await conn_record.metadata_get(
                    session=session, key="reuse_msg_id"
                )
                assert thread_reuse_msg_id == conn_reuse_msg_id
                await conn_record.metadata_set(
                    session=session, key="reuse_msg_state", value="accepted"
                )
        except Exception as e:
            raise OutOfBandManagerError(
                (
                    (
                        "Error processing reuse accepted message "
                        f"for OOB invitation {invi_msg_id}, {e}"
                    )
                )
            )

    async def receive_problem_report(
        self,
        problem_report: OOBProblemReport,
        receipt: MessageReceipt,
        conn_record: ConnRecord,
    ) -> None:
        """
        Receive and process a ProblemReport message from the inviter to invitee.

        Process a `ProblemReport` message by updating the ConnRecord metadata
        state to `not_accepted`.

        Args:
            problem_report: The `OOBProblemReport` to process
            receipt: The message receipt

        Returns:

        Raises:
            OutOfBandManagerError: if there is an error in processing the
            HandshakeReuseAccept message

        """
        try:
            invi_msg_id = problem_report._thread.pthid
            thread_reuse_msg_id = problem_report._thread.thid
            async with self.profile.session() as session:
                conn_reuse_msg_id = await conn_record.metadata_get(
                    session=session, key="reuse_msg_id"
                )
                assert thread_reuse_msg_id == conn_reuse_msg_id
                await conn_record.metadata_set(
                    session=session, key="reuse_msg_state", value="not_accepted"
                )
        except Exception as e:
            raise OutOfBandManagerError(
                (
                    (
                        "Error processing problem report message "
                        f"for OOB invitation {invi_msg_id}, {e}"
                    )
                )
            )
