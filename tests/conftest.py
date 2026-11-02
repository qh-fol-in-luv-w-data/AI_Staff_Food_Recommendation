from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from aistaff.config import load_store
from aistaff.dialog import DialogManager
from aistaff.storage import Storage

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "config" / "stores" / "quan-ngon"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Thời điểm cố định để test ưu đãi theo giờ
TUE_HAPPY = datetime(2026, 11, 3, 15, 0, tzinfo=TZ)   # thứ Ba 15:00: giờ vàng + combo thứ Ba
WED_MORNING = datetime(2026, 11, 4, 9, 0, tzinfo=TZ)  # thứ Tư 9:00: chỉ ưu đãi cả ngày
SAT_NOON = datetime(2026, 11, 7, 12, 0, tzinfo=TZ)    # thứ Bảy: cuối tuần


@pytest.fixture(scope="session")
def cfg():
    return load_store(STORE)


@pytest.fixture
def storage():
    s = Storage(":memory:")
    yield s
    s.close()


@pytest.fixture
def make_dm(cfg, storage):
    def _make(now=WED_MORNING):
        return DialogManager(cfg, storage, now_fn=lambda: now)

    return _make
