"""Test IndySDK Wallet import and export through profile manager"""
# pylint: disable=redefined-outer-name

import json
from pathlib import Path

import pytest

from aries_cloudagent.config.base_context import InjectionContext
from aries_cloudagent.core.error import ProfileError
from aries_cloudagent.indy.sdk.profile import IndySdkProfile, IndySdkProfileManager
from aries_cloudagent.ledger.indy import IndySdkLedgerPool
from aries_cloudagent.storage.base import BaseStorage
from aries_cloudagent.storage.error import StorageNotFoundError
from aries_cloudagent.storage.record import StorageRecord


@pytest.fixture
async def manager():
    "Indy SDK profile manager."
    yield IndySdkProfileManager()


@pytest.fixture
def context():
    """Injection context."""
    context = InjectionContext(enforce_typing=False, settings={})
    context.injector.bind_instance(IndySdkLedgerPool, IndySdkLedgerPool("name"))
    yield context


@pytest.fixture
def wallet_config(tmp_path):
    """Wallet configuration."""
    yield {"storage_config": json.dumps({"path": str(tmp_path)})}


@pytest.fixture
async def provisioned_profile(manager, context, wallet_config):
    """A provisioned indy profile."""
    profile: IndySdkProfile = await manager.provision(
        context=context, config=wallet_config
    )
    assert not await has_record_with_id(profile, "test", "test")
    async with profile.session() as session:
        storage = session.inject(BaseStorage)
        await storage.add_record(
            StorageRecord("test", "test", {"test": "value"}, id="test")
        )
    yield profile
    if profile.opened:
        await profile.remove()


async def has_record_with_id(profile: IndySdkProfile, type_: str, id_: str):
    """Assert the profile has a record with id"""
    async with profile.session() as session:
        storage = session.inject(BaseStorage)
        try:
            await storage.get_record(type_, id_)
            return True
        except StorageNotFoundError:
            return False


@pytest.mark.asyncio
@pytest.mark.indy
async def test_import_export(
    context: InjectionContext,
    manager: IndySdkProfileManager,
    provisioned_profile: IndySdkProfile,
    tmp_path: Path,
    wallet_config,
):
    """Test the round trip import and export."""
    export_path = tmp_path / "exported_wallet"
    await manager.export_to_file(
        provisioned_profile, export_path, key="test", config=wallet_config
    )
    await provisioned_profile.remove()
    imported = await manager.import_from_file(
        context, export_path, key="test", config=wallet_config
    )
    assert await has_record_with_id(imported, "test", "test")
    await imported.remove()


@pytest.mark.asyncio
@pytest.mark.indy
async def test_export_x_bad_path(
    manager: IndySdkProfileManager,
    provisioned_profile: IndySdkProfile,
):
    """Test exporting to a bad path raises error"""
    with pytest.raises(ProfileError):
        await manager.export_to_file(provisioned_profile, Path(""), key="test")


@pytest.mark.asyncio
@pytest.mark.indy
async def test_import_x_bad_path(
    context: InjectionContext,
    manager: IndySdkProfileManager,
):
    """Test importing from a bad path raises error"""
    with pytest.raises(ProfileError):
        await manager.import_from_file(context, Path(""), key="test")


@pytest.mark.asyncio
@pytest.mark.indy
async def test_import_x_path_does_not_exist(
    context: InjectionContext,
    manager: IndySdkProfileManager,
    tmp_path: Path,
):
    """Test importing from a non-existant path raises error"""
    with pytest.raises(ProfileError):
        await manager.import_from_file(context, tmp_path / "does not exist", key="test")


@pytest.mark.asyncio
@pytest.mark.indy
async def test_indy_requires_keys(
    context: InjectionContext,
    provisioned_profile: IndySdkProfile,
    manager: IndySdkProfileManager,
    tmp_path: Path,
):
    """Test not passing keys raises error"""
    with pytest.raises(ValueError):
        await manager.import_from_file(context, tmp_path / "does not exist")

    with pytest.raises(ValueError):
        await manager.export_to_file(provisioned_profile, tmp_path / "exported_wallet")
