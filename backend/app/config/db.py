from pymongo import MongoClient
from app.config.settings import MONGO_URI, DB_NAME

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Collections — import these directly wherever you need DB access.
users_col = db["users"]
instruments_col = db["instruments"]
applications_col = db["applications"]
inspections_col = db["inspections"]
certificates_col = db["certificates"]
alerts_col = db["alerts"]


def init_indexes():
    """Call once at startup to make sure key fields are indexed/unique."""
    users_col.create_index("email", unique=True)
    instruments_col.create_index("serial_no", unique=True)
    applications_col.create_index("status")
    certificates_col.create_index("cert_no", unique=True)
