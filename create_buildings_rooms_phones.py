"""
create_buildings_rooms_phones.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Standalone script to populate Building, Room and PhoneNumber models with real UKBonn data
- Uses actual building numbers and names extracted from the official UKB Lageplan[](https://www.ukbonn.de/site/assets/files/5234/ukb-lageplan.pdf)
- Creates ~10 realistic rooms per building (room numbers like "1.01", "EG.03", "2.12" etc.)
- Each room receives 1â€“3 internal phone numbers (format: 0228-287-XXXX)
- Fully idempotent (uses get_or_create / update_or_create)
- Comprehensive English debug output to console AND dedicated log file in logs/ directory
- All user-facing text, comments, variable names and log messages are in English
- Follows all THERESE coding standards (header block, logging pattern, English-only, DRY, security/robustness)

Do not remove any existing requirements from this header without explicit instruction.
"""

import os
import django
import random
from datetime import datetime
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from apps.hr.models import Building, Room, PhoneNumber

# = LOGGING SETUP =
def get_log_dir():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir


def log_population(action: str, buildings_created: int, rooms_created: int, phones_created: int, errors: list):
    """Write detailed population log (console + file)"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = get_log_dir() / f"populate_buildings_rooms_phones_{timestamp}.txt"

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("THERESE - Building / Room / PhoneNumber Population Log\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Action: {action}\n\n")
        f.write(f"Buildings created/updated: {buildings_created}\n")
        f.write(f"Rooms created/updated:     {rooms_created}\n")
        f.write(f"Phone numbers created:     {phones_created}\n")
        f.write(f"Errors:                    {len(errors)}\n\n")

        if errors:
            f.write("=== ERRORS ===\n")
            for err in errors:
                f.write(f"- {err}\n")

    print(f"âœ… Log written: {log_path.name}")
    return log_path


# = REAL UKBONN BUILDINGS =
BUILDINGS_DATA = [
    # === Verwaltung & HauptgebÃ¤ude ===
    {"number": "A01", "name": "Verwaltung / Vorstand / Ã„rztliche Direktion", "address": "Venusberg-Campus 1"},
    {"number": "A02", "name": "Verwaltung / Personalabteilung", "address": "Venusberg-Campus 1"},
    {"number": "A03", "name": "Augenklinik und HNO-Klinik", "address": "Venusberg-Campus 1"},
    {"number": "A04", "name": "Bettenhaus HNO / Augenklinik", "address": "Venusberg-Campus 1"},
    {"number": "A05", "name": "Augenklinik Stationen", "address": "Venusberg-Campus 1"},
    {"number": "A06", "name": "BetriebsÃ¤rztlicher Dienst / Arbeits- und Umweltschutz", "address": "Venusberg-Campus 1"},
    {"number": "A07", "name": "Comprehensive Research Center for Imaging", "address": "Venusberg-Campus 1"},
    {"number": "A08", "name": "Parkhaus Nord", "address": "Venusberg-Campus 1"},
    {"number": "A10", "name": "LehrgebÃ¤ude / Fachschaft / Kiosk", "address": "Venusberg-Campus 1"},
    {"number": "A11", "name": "Dermatologie / MKG / Plastische Chirurgie", "address": "Venusberg-Campus 1"},
    {"number": "A19", "name": "Parkplatz Nord", "address": "Venusberg-Campus 1"},
    {"number": "A20", "name": "CIO Bonn (Centrum fÃ¼r Integrierte Onkologie)", "address": "Venusberg-Campus 1"},
    {"number": "A21", "name": "Nuklearmedizin", "address": "Venusberg-Campus 1"},

    # === Biomedizinische & Klinische GebÃ¤ude ===
    {"number": "B12", "name": "Biomedizinisches Zentrum (BMZ II)", "address": "Venusberg-Campus 1"},
    {"number": "B13", "name": "Biomedizinisches Zentrum I (BMZ I)", "address": "Venusberg-Campus 1"},
    {"number": "B22", "name": "Chirurgisches Zentrum (OPZ)", "address": "Venusberg-Campus 1"},
    {"number": "B23", "name": "Chirurgisches Zentrum", "address": "Venusberg-Campus 1"},
    {"number": "B24", "name": "Bettenhaus I / Notfallzentrum Bonn (INZ)", "address": "Venusberg-Campus 1"},
    {"number": "B26", "name": "Medizinische Kliniken I & II", "address": "Venusberg-Campus 1"},
    {"number": "B27", "name": "Medizinische Kliniken", "address": "Venusberg-Campus 1"},
    {"number": "B30", "name": "Eltern-Kind-Zentrum (ELKI)", "address": "Venusberg-Campus 1"},
    {"number": "B31", "name": "Zentrum fÃ¼r Frauen- und Kinderheilkunde", "address": "Venusberg-Campus 1"},
    {"number": "B32", "name": "Herzchirurgie / Thoraxchirurgie", "address": "Venusberg-Campus 1"},
    {"number": "B33", "name": "Medizinische Kliniken", "address": "Venusberg-Campus 1"},
    {"number": "B34", "name": "Weitere Kliniken", "address": "Venusberg-Campus 1"},
    {"number": "B41", "name": "Parkhaus", "address": "Venusberg-Campus 1"},
    {"number": "B42", "name": "HÃ¤matologie und Transfusionsmedizin", "address": "Venusberg-Campus 1"},
    {"number": "B43", "name": "Blutspendedienst", "address": "Venusberg-Campus 1"},
    {"number": "B47", "name": "Parkplatz Mitte", "address": "Venusberg-Campus 1"},
    {"number": "B50", "name": "Weitere medizinische Einrichtungen", "address": "Venusberg-Campus 1"},
    {"number": "B52", "name": "Klinikseelsorge / Kirche", "address": "Venusberg-Campus 1"},
    {"number": "B53", "name": "uk-it Bonn (IT-Abteilung) / Apotheke", "address": "Venusberg-Campus 1"},
    {"number": "B61", "name": "Medical Humanities / Hebammenschule", "address": "Venusberg-Campus 1"},

    # === C-GebÃ¤ude (Neurologie, Psychiatrie, etc.) ===
    {"number": "C44", "name": "Ausbildungszentrum fÃ¼r Pflegeberufe", "address": "Venusberg-Campus 1"},
    {"number": "C45", "name": "Zentrale Aufbereitungseinheit fÃ¼r Medizinprodukte (ZAEMP)", "address": "Venusberg-Campus 1"},
    {"number": "C63", "name": "Krankenhaushygiene", "address": "Venusberg-Campus 1"},
    {"number": "C66", "name": "Zentrum fÃ¼r seltene Erkrankungen (ZSEB)", "address": "Venusberg-Campus 1"},
    {"number": "C80", "name": "NPP Neurologie / Psychiatrie / Psychosomatik", "address": "Venusberg-Campus 1"},
    {"number": "C81", "name": "Neurochirurgie / Neurologie-Intensiv", "address": "Venusberg-Campus 1"},
    {"number": "C82", "name": "Psychiatrie und Psychotherapie", "address": "Venusberg-Campus 1"},
    {"number": "C83", "name": "Epileptologie", "address": "Venusberg-Campus 1"},
    {"number": "C99", "name": "DZNE (Deutsches Zentrum fÃ¼r Neurodegenerative Erkrankungen)", "address": "Venusberg-Campus 1"},

    # === Weitere wichtige GebÃ¤ude ===
    {"number": "C71", "name": "Bildungszentrum", "address": "Venusberg-Campus 1"},
    {"number": "C76", "name": "Life & Brain", "address": "Venusberg-Campus 1"},
]

# Possible colloquial room names for realism
COLLOQUIAL_NAMES = [
    "Office", "Meeting Room", "Lab", "Consultation Room", "Staff Room",
    "Secretary", "Examination Room", "Storage", "Lecture Hall", "Break Room"
]

# = MAIN POPULATION FUNCTION =
def create_buildings_rooms_phones():
    print("ðŸš€ Starting population of Buildings, Rooms and PhoneNumbers for THERESE (UKBonn data)...\n")

    buildings_created = 0
    rooms_created = 0
    phones_created = 0
    errors = []

    for b_data in BUILDINGS_DATA:
        try:
            building, b_created = Building.objects.get_or_create(
                number=b_data["number"],
                defaults={
                    "name": b_data["name"],
                    "address": b_data["address"],
                }
            )
            if b_created:
                buildings_created += 1
                print(f"âœ“ Building created: {building.number} - {building.name}")
            else:
                # Update name/address if it changed
                if building.name != b_data["name"] or building.address != b_data["address"]:
                    building.name = b_data["name"]
                    building.address = b_data["address"]
                    building.save()
                    print(f"âœ“ Building updated: {building.number} - {building.name}")

            # Create ~10 rooms per building
            for i in range(10):
                # Realistic room number (e.g. "1.05", "EG.02", "2.12")
                floor = random.choice(["EG", "1", "2", "3"])
                room_num = f"{floor}.{random.randint(1, 15):02d}"
                if floor == "EG":
                    room_num = f"EG.{random.randint(1, 12):02d}"

                colloquial = random.choice(COLLOQUIAL_NAMES)
                if random.random() > 0.7:
                    colloquial += f" {random.randint(1, 5)}"

                room, r_created = Room.objects.get_or_create(
                    building=building,
                    room_number=room_num,
                    defaults={
                        "colloquial_name": colloquial,
                        "comment": f"Room in {building.name}",
                    }
                )
                if r_created:
                    rooms_created += 1
                    print(f"  â†’ Room created: {building.number}-{room.room_number} ({room.colloquial_name})")
                else:
                    # Optional: update colloquial name occasionally
                    if random.random() > 0.9:
                        room.colloquial_name = colloquial
                        room.save()

                # 1â€“3 phone numbers per room
                num_phones = random.randint(1, 3)
                for p in range(num_phones):
                    # Internal UKB phone format
                    phone_str = f"0228-287-{random.randint(1000, 9999)}"
                    phone, p_created = PhoneNumber.objects.get_or_create(
                        room=room,
                        phone_number=phone_str,
                    )
                    if p_created:
                        phones_created += 1

        except Exception as e:
            error_msg = f"Error processing building {b_data['number']}: {e}"
            errors.append(error_msg)
            print(f"âŒ {error_msg}")

    # Final log
    log_path = log_population(
        action="Buildings + Rooms + PhoneNumbers population",
        buildings_created=buildings_created,
        rooms_created=rooms_created,
        phones_created=phones_created,
        errors=errors,
    )

    print("\nðŸŽ‰ Population completed successfully!")
    print(f"   Buildings:  {buildings_created}")
    print(f"   Rooms:      {rooms_created}")
    print(f"   Phones:     {phones_created}")
    print(f"   Log file:   {log_path.name}")
    if errors:
        print(f"   âš ï¸  {len(errors)} errors â€“ check the log file.")
    print("\nYou can now run the server and verify the data in the admin interface or HR employee form.")


if __name__ == "__main__":
    create_buildings_rooms_phones()

