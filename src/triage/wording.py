"""Formulations standard des évaluations : communes aux vignettes d'entraînement et au service
(message réécrit quand un garde-fou relève le niveau). Module sans dépendance : l'API l'importe."""

PRIORITY_LABEL = {"maximale": "MAXIMALE", "moderee": "MODÉRÉE", "differee": "DIFFÉRÉE"}
EXPLANATION = {
    "maximale": "Votre situation peut s'aggraver rapidement : un soignant doit vous prendre en "
    "charge sans attendre.",
    "moderee": "Votre situation doit être évaluée rapidement par un médecin, mais les éléments "
    "recueillis ne montrent pas de danger vital immédiat. Signalez tout de suite à l'accueil "
    "toute aggravation.",
    "differee": "Votre situation ne semble pas urgente : vous serez pris en charge après les "
    "patients les plus graves. Prévenez l'accueil si vos symptômes s'aggravent.",
}
ORIENTATION = {
    "1": "prise en charge immédiate en salle d'accueil des urgences vitales et appel du médecin.",
    "2": "installation rapide en box, avis médical sans délai et surveillance continue.",
    "3A": "évaluation médicale rapide ; réévaluer les constantes en attendant, car le risque "
    "d'aggravation est réel.",
    "3B": "évaluation médicale rapide ; réévaluer régulièrement le patient en attendant.",
    "4": "prise en charge non urgente en circuit court ; réévaluer en cas d'aggravation.",
    "5": "prise en charge non urgente ; une consultation de médecine générale peut être proposée.",
}
