"""
GROUP_REGISTRY — categorías y grupos de Telegram para ingesta de ofertas.

Organización por categorías con prioridad y respaldo (backup).
Cada grupo define su formato de parsing, prioridad y estado.
"""

GROUP_REGISTRY = {
    # ── STEM Costa Rica ──────────────────────────────────────────
    "stem_cr": {
        "label": "STEM Costa Rica",
        "search_keywords": [
            "developer", "ingeniero", "software", "devops", "data",
            "programador", "desarrollador", "engineer", "programmer",
            "costa rica", "san josé", "heredia", "alajuela",
        ],
        "groups": [
            {
                "id": "stem_cr_primary",
                "name": "STEM Jobs CR",
                "telegram_channel": "STEMJobsCR",
                "priority": 1,
                "format_template": "stem_jobscr",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
            },
            {
                "id": "stem_cr_backup1",
                "name": "STEM Jobs LATAM",
                "telegram_channel": "STEMJobsLATAM",
                "priority": 2,
                "format_template": "stem_latam",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
            },
            {
                "id": "stem_cr_backup2",
                "name": "Empleos Tech CR",
                "telegram_channel": "EmpleosTechCR",
                "priority": 3,
                "format_template": "freetext",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
            },
            {
                "id": "stem_cr_backup3",
                "name": "Trabajos IT Costa Rica",
                "telegram_channel": "TrabajosITCR",
                "priority": 4,
                "format_template": "freetext",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
            },
        ],
        "admin_alert_email": "",
        "demand_score": 0,
        "last_polled": None,
        "poll_interval_hours": 24,
    },

    # ── LATAM Remoto ────────────────────────────────────────────
    "latam_remote": {
        "label": "LATAM Remoto",
        "search_keywords": [
            "remote", "remoto", "latam", "100% remoto", "trabajo remoto",
            "home office", "work from home", "cualquier país",
        ],
        "groups": [
            {
                "id": "latam_remote_primary",
                "name": "Vacantes Remotas",
                "telegram_channel": "vacantesremotas",
                "priority": 1,
                "format_template": "vacantes_remotas",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
            },
        ],
        "admin_alert_email": "",
        "demand_score": 0,
        "last_polled": None,
        "poll_interval_hours": 24,
    },

    # ── Freelance Internacional ──────────────────────────────────
    "freelance_intl": {
        "label": "Freelance Internacional",
        "search_keywords": [
            "freelance", "freelancer", "contractor", "remoto", "remote",
            "part-time", "medio tiempo", "proyecto", "project",
        ],
        "groups": [
            {
                "id": "freelance_intl_primary",
                "name": "IT Freelancers",
                "telegram_channel": "itfreelancers",
                "priority": 1,
                "format_template": "it_freelancers",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
            },
        ],
        "admin_alert_email": "",
        "demand_score": 0,
        "last_polled": None,
        "poll_interval_hours": 24,
    },

    # ── From Work Home (filtrado — mayormente spam/gigs) ─────────
    "from_work_home": {
        "label": "From Work Home (filtrado)",
        "search_keywords": [
            "remote", "work from home", "home office", "online job",
            "data entry", "virtual assistant",
        ],
        "groups": [
            {
                "id": "from_work_home_primary",
                "name": "From Work Home",
                "telegram_channel": "from_work_home",
                "priority": 1,
                "format_template": "from_work_home",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
                "low_priority": True,  # Marcar como fuente de baja prioridad
            },
        ],
        "admin_alert_email": "",
        "demand_score": 0,
        "last_polled": None,
        "poll_interval_hours": 48,  # Poll menos frecuente por ser low priority
    },

    # ── STEM Dinamarca (legacy) ──────────────────────────────────
    "stem_dk": {
        "label": "STEM Dinamarca",
        "search_keywords": [
            "denmark", "danmark", "copenhagen", "københavn", "danish",
        ],
        "groups": [
            {
                "id": "stem_dk_primary",
                "name": "STEM Jobs LATAM",  # Reuses for remote-DK-friendly roles
                "telegram_channel": "STEMJobsLATAM",
                "priority": 1,
                "format_template": "stem_latam",
                "status": "active",
                "last_success": None,
                "consecutive_failures": 0,
            },
        ],
        "admin_alert_email": "",
        "demand_score": 0,
        "last_polled": None,
        "poll_interval_hours": 24,
    },
}

# Nota: categorías SIN backup suficiente:
# - latam_remote: solo 1 grupo (vacantesremotas). Sin backup.
# - freelance_intl: solo 1 grupo (itfreelancers). Sin backup.
# - from_work_home: solo 1 grupo, fuente de baja prioridad.
# Lo ideal sería agregar 1-2 grupos extra por categoría cuando se identifiquen.
