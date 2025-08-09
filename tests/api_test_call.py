import requests
import os

# Basis-URL der API
base_url = "http://localhost:8000"

# Daten für die POST-Anfrage an den /api/export-Endpunkt
# Samples müssen Gewebe- und Krankheitszuordnung Zuweisung besitzen
post_data = {
    "sample_list": [
        "GSM400180",
        "GSM400181",
        "GSM400182",
        "GSM400183"
    ],
    "normalization_method": "quantile",     # minmax, zscore, quantile
    "logTransform": True
}


headers = {
    "Content-Type": "application/json"
}

# POST-Anfrage für /api/export
export_url = f"{base_url}/api/export"
export_response = requests.post(export_url, json=post_data, headers=headers)

# Verzeichnis erstellen, falls nicht vorhanden
output_dir = "api_test"
os.makedirs(output_dir, exist_ok=True)

# Ergebnis überprüfen und Dateien speichern
if export_response.status_code == 200:
    response_json = export_response.json()
    print("Response:", response_json)
    with open(os.path.join(output_dir, "gene_expression_matrix.csv"), "w") as file:
        file.write(response_json["gene_expression"])
    with open(os.path.join(output_dir, "sample_metadata.csv"), "w") as file:
        file.write(response_json["metadata"])
    print("CSV-Dateien erfolgreich exportiert und gespeichert.")
    if response_json.get("missing_samples"):
        print("Fehlende Proben:", response_json["missing_samples"])
else:
    print("Fehler beim Exportieren der CSV-Dateien:", export_response.json())
