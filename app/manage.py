"""Explicit schema initialization for new databases only. Never run on a live existing DB."""
import sys
from sqlalchemy import select
from .core import Base, Category, SessionLocal, engine

CATEGORIES = [
    ("dust_storm", "Dust and sand storm", "عاصفة غبارية أو رملية"),
    ("heatwave", "Heatwave", "موجة حر"),
    ("flood", "Flood", "فيضان"),
    ("drought", "Drought and water shortage", "جفاف وشح المياه"),
    ("salinity", "Salinity intrusion", "تداخل الملوحة"),
    ("fish_kill", "Fish kill", "نفوق الأسماك"),
    ("oil_spill", "Oil spill", "تسرب نفطي"),
    ("industrial_discharge", "Industrial discharge", "تصريف صناعي"),
    ("waste_dumping", "Waste dumping", "رمي النفايات"),
    ("air_pollution", "Air pollution", "تلوث الهواء"),
    ("wildfire", "Wildfire", "حريق غابات"),
]


def init():
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        for code, en, ar in CATEGORIES:
            if session.scalar(select(Category.id).where(Category.code == code)) is None:
                session.add(Category(code=code, label_en=en, label_ar=ar))


if __name__ == "__main__":
    if sys.argv[1:] != ["init"]:
        raise SystemExit("Usage: python -m app.manage init  # for a NEW empty database only")
    init()
    print("Schema and category reference data initialized")
