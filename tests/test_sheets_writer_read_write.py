from unittest.mock import patch, MagicMock
from src.sheets_writer import read_from_sheet, write_enriched_sheet


def _mock_client(records=None, headers=None):
    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = records or []
    mock_sheet.row_values.return_value = headers or []
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_sheet
    mock_spreadsheet.add_worksheet.return_value = mock_sheet
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet
    return mock_client, mock_sheet


def test_read_from_sheet_returns_records():
    records = [{"Company Name": "Acme", "Website": "https://acme.com"}]
    client, _ = _mock_client(records=records)
    with patch("src.sheets_writer._get_client", return_value=client):
        result = read_from_sheet("fake_id", "Sheet1")
    assert result == records


def test_write_enriched_sheet_calls_update():
    client, mock_sheet = _mock_client()
    rows = [
        {
            "Company Name": "Acme", "Website": "https://acme.com",
            "tuyen_dung": "Tuyển BE", "blog": "", "linh_vuc": "Fintech",
            "du_an_gan_nhat": "", "doi_tac": "VCB",
        }
    ]
    with patch("src.sheets_writer._get_client", return_value=client):
        write_enriched_sheet(rows, "fake_id", "Enriched")
    mock_sheet.update.assert_called_once()
