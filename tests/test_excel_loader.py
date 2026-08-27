import pandas as pd
import pytest

from src.ingestion.excel_loader import ExcelValidationError, load_passengers


def test_load_valid_passengers(tmp_path):
    df = pd.DataFrame([
        {"identificador": "1", "nombre": "Ana", "direccion": "Calle 1 #2-3", "turno": "mañana"},
        {"identificador": "2", "nombre": "Luis", "direccion": "Calle 4 #5-6", "turno": "tarde"},
    ])
    file_path = tmp_path / "pasajeros.xlsx"
    df.to_excel(file_path, index=False)

    passengers = load_passengers(file_path)

    assert len(passengers) == 2
    assert passengers[0].nombre == "Ana"
    assert passengers[0].direccion_original == "Calle 1 #2-3"


def test_missing_required_column_raises(tmp_path):
    df = pd.DataFrame([{"nombre": "Ana", "direccion": "Calle 1"}])  # falta 'identificador'
    file_path = tmp_path / "pasajeros.xlsx"
    df.to_excel(file_path, index=False)

    with pytest.raises(ExcelValidationError):
        load_passengers(file_path)


def test_empty_required_fields_are_discarded(tmp_path):
    df = pd.DataFrame([
        {"identificador": "1", "nombre": "Ana", "direccion": "Calle 1"},
        {"identificador": None, "nombre": "Sin id", "direccion": "Calle 2"},
    ])
    file_path = tmp_path / "pasajeros.xlsx"
    df.to_excel(file_path, index=False)

    passengers = load_passengers(file_path)

    assert len(passengers) == 1
    assert passengers[0].nombre == "Ana"


def test_unsupported_extension_raises(tmp_path):
    file_path = tmp_path / "pasajeros.txt"
    file_path.write_text("dummy")

    with pytest.raises(ExcelValidationError):
        load_passengers(file_path)


def test_nonexistent_file_raises(tmp_path):
    with pytest.raises(ExcelValidationError):
        load_passengers(tmp_path / "no_existe.xlsx")
