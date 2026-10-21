"""Site-type filters shared by the providers."""

# Site types most people aren't looking for: horse camps, group areas, day-use
# pavilions/picnic areas, shelters and cabins.
SPECIALTY_WORDS = ("equestrian", "horse", "group", "pavilion", "picnic", "shelter", "cabin", "management")


def is_specialty(site_type):
    t = (site_type or "").lower()
    return any(w in t for w in SPECIALTY_WORDS)
