from scripts.evaluate_v4 import extraction, metrics


def test_positive_abstention_stays_in_overall_recall_and_negative_abstention_in_fpr_denominator():
    rows = [
        {"truth": 1, "predicted": 1, "sufficient": True, "elapsed_ms": 1},
        {"truth": 1, "predicted": 0, "sufficient": False, "elapsed_ms": 2},
        {"truth": 0, "predicted": 1, "sufficient": True, "elapsed_ms": 3},
        {"truth": 0, "predicted": 0, "sufficient": False, "elapsed_ms": 4},
    ]
    result = metrics(rows)
    assert result["recall"] == 0.5 and result["fpr"] == 0.5
    assert result["processed_recall"] == 1 and result["processed_fpr"] == 1
    assert result["insufficient"] == 2 and result["coverage"] == 0.5
    assert result["precision_ci"][0] < 0.5 < result["precision_ci"][1]


def test_candidate_is_not_automatic_success_and_empty_query_is_not_referral_sample():
    correct = "https://p5.test/path?ref=A7"
    wrong = "https://p5.test/path?ref=A8"
    rows = [
        {
            "id": "a",
            "materials": [
                {
                    "image": True,
                    "raw_urls": [wrong],
                    "automatic_urls": [],
                    "candidates": [wrong, correct],
                    "qr_payloads": [],
                },
                {
                    "image": True,
                    "raw_urls": ["https://p6.test/"],
                    "automatic_urls": ["https://p6.test/"],
                    "candidates": ["https://p6.test/"],
                    "qr_payloads": [],
                },
            ],
        }
    ]
    labels = {
        "a": {
            "materials": [
                {"ocr_urls": [correct], "qr_payloads": []},
                {"ocr_urls": ["https://p6.test/"], "qr_payloads": []},
            ]
        }
    }
    result = extraction(rows, labels)
    assert result["raw_url"]["fp"] == 1 and result["raw_url"]["fn"] == 1
    assert result["automatic_url"]["fp"] == 0 and result["automatic_url"]["fn"] == 1
    assert result["raw_domain"]["recall"] == 1
    assert result["raw_referral"]["n"] == 1 and result["raw_referral"]["recall"] == 0
    assert result["correct_candidate_available"] == 2
    assert result["qr_expected"]["n"] == 0 and result["qr_expected"]["precision"] is None
