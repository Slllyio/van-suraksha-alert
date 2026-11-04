"""Division -> forest zone mapping, from Champion & Seth forest-type geography of MP. Approximate: a division holds
several types, this names the dominant one. Project/FDC divisions are MPRVVN production forests whatever the species."""
SAL = {"North_Balaghat", "South_Balaghat", "East_Mandla", "West_Mandla", "Dindori", "Kanha Tiger Reserve", "Anuppur",
       "North_Shahdol", "South_Shahdol", "Umaria", "BTR", "Sidhi", "SANJAY_DUBRI", "Singrauli", "Rewa", "Satna"}
TEAK = {"North_Betul", "South_Betul", "West_Betul", "Harda", "Hoshangabad", "Satpura_TR", "Khandwa", "Burhanpur", "Barwah",
        "Khargone", "Sendhwa", "Barwani", "Dewas", "East_Chhindwara", "West_Chhindwara", "South_Chhindwara", "North_Seoni",
        "South_Seoni", "PTR MP", "Narsinghpur", "Sehore", "Obedullahganj", "Raisen", "Bhopal", "Jabalpur", "Katni", "Damoh"}


def zone(division: str) -> str:
    n = division.lower()
    if "proj" in n or "fdc" in n:
        return "plantation_mprvvn"
    if division in SAL:
        return "sal_belt"
    if division in TEAK:
        return "teak_belt"
    return "mixed_dry_deciduous"


if __name__ == "__main__":
    assert zone("Lamta_Proj_N_Balaghat") == "plantation_mprvvn" and zone("FDC_Khandwa") == "plantation_mprvvn"
    assert zone("Singrauli") == "sal_belt" and zone("Harda") == "teak_belt" and zone("Guna") == "mixed_dry_deciduous"
    print("ok")
