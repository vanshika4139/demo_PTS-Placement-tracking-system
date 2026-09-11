# Fixed-ID list of Indian States and Union Territories, used for the
# Organization "State" dropdown (Super Admin > Organizations).
#
# IDs are hardcoded and must never be renumbered once organizations start
# referencing them via organization.state_id - treat this list as append-only.
# There is no dedicated states/districts master table in this project yet,
# so this lightweight list stands in for one (see Notes to product owner
# re: Organization Management KYC/geography gaps).

INDIAN_STATES = [
    (1, "Andhra Pradesh"),
    (2, "Arunachal Pradesh"),
    (3, "Assam"),
    (4, "Bihar"),
    (5, "Chhattisgarh"),
    (6, "Goa"),
    (7, "Gujarat"),
    (8, "Haryana"),
    (9, "Himachal Pradesh"),
    (10, "Jharkhand"),
    (11, "Karnataka"),
    (12, "Kerala"),
    (13, "Madhya Pradesh"),
    (14, "Maharashtra"),
    (15, "Manipur"),
    (16, "Meghalaya"),
    (17, "Mizoram"),
    (18, "Nagaland"),
    (19, "Odisha"),
    (20, "Punjab"),
    (21, "Rajasthan"),
    (22, "Sikkim"),
    (23, "Tamil Nadu"),
    (24, "Telangana"),
    (25, "Tripura"),
    (26, "Uttar Pradesh"),
    (27, "Uttarakhand"),
    (28, "West Bengal"),
    (29, "Andaman and Nicobar Islands"),
    (30, "Chandigarh"),
    (31, "Dadra and Nagar Haveli and Daman and Diu"),
    (32, "Delhi"),
    (33, "Jammu and Kashmir"),
    (34, "Ladakh"),
    (35, "Lakshadweep"),
    (36, "Puducherry"),
]

INDIAN_STATES_BY_ID = {state_id: name for state_id, name in INDIAN_STATES}


def state_name(state_id):
    """Resolve a stored state_id back to its display name. Returns '-' for
    None/unknown IDs so templates don't need to special-case missing data."""
    if state_id is None:
        return "-"
    return INDIAN_STATES_BY_ID.get(state_id, "-")