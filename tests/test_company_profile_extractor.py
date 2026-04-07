from src.company_profile_extractor import CompanyProfileExtractor


def test_extract_returns_five_keys():
    """Kết quả luôn có đủ 5 key dù không tìm thấy gì."""
    extractor = CompanyProfileExtractor.__new__(CompanyProfileExtractor)
    result = extractor._parse("[]")
    assert set(result.keys()) == {"tuyen_dung", "blog", "linh_vuc", "du_an_gan_nhat", "doi_tac"}


def test_parse_valid_json():
    extractor = CompanyProfileExtractor.__new__(CompanyProfileExtractor)
    raw = '''
    {
      "tuyen_dung": "Tuyển Senior Backend",
      "blog": "https://company.com/blog",
      "linh_vuc": "Fintech, Payments",
      "du_an_gan_nhat": "Dự án ABC cho VCB",
      "doi_tac": "Vietcombank, NAPAS"
    }
    '''
    result = extractor._parse(raw)
    assert result["tuyen_dung"] == "Tuyển Senior Backend"
    assert result["linh_vuc"] == "Fintech, Payments"
    assert result["doi_tac"] == "Vietcombank, NAPAS"


def test_parse_invalid_json_returns_empty_strings():
    extractor = CompanyProfileExtractor.__new__(CompanyProfileExtractor)
    result = extractor._parse("không phải json")
    assert result["tuyen_dung"] == ""
    assert result["blog"] == ""
