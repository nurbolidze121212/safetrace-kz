from backend.network_signals import build_signals


def record(key, text):
    return {"id": key, "text": text, "fingerprint": key, "evidence_ids": [key + "-source"], "scopes": []}


def test_weak_hypothesis_is_separate_from_exact_evidence():
    a = record("a", "Разные сообщения не похожи")
    b = record("b", "Другие слова в публикации")
    for r, host in [(a, "example12.test"), (b, "example33.test")]:
        r["urls"] = [{"value": "https://" + host, "evidence_ids": [r["id"] + "-url"]}]
    result = build_signals([a, b])
    assert result["counts"]["strong"] == 0 and result["counts"]["weak"] == 1
    edge = result["edges"][0]
    assert edge["basis"] == "numbered_domain" and edge["strength"] == "weak"
    assert set(edge["evidence_ids"]) == {"a-url", "b-url"}
    assert build_signals([a, b], include_weak=False)["edges"] == []


def test_shared_infrastructure_needs_observations_and_cannot_imply_ownership():
    a, b = record("a", "one"), record("b", "two")
    for r in (a, b):
        r["infrastructure"] = [{"value": "shared-cdn-ip", "evidence_ids": [r["id"] + "-observed-ip"]}]
    result = build_signals([a, b])
    assert result["edges"][0]["meaning"] == "hypothesis; not ownership or risk"
    assert abs(sum(result["pagerank"].values()) - 1) < 1e-6
    assert len(result["communities"]) == 2, "Shared hosting alone must not merge investigation groups"


def test_two_bases_link_weak_materials_but_remain_hypotheses():
    a, b = record("a", "Переходите на эту новую страницу и забирайте свой подарок сегодня"), record("b", "Переходите на эту новую страницу и забирайте свой подарок завтра")
    for r in (a, b):
        r["promos"] = [{"value": "SAMPLE99", "evidence_ids": [r["id"] + "-promo"]}]
    result = build_signals([a, b])
    assert result["counts"]["strong"] == 0
    assert len(result["communities"]) == 1


def test_common_boilerplate_does_not_expand_quadratically():
    records = [record(str(i), "Общий текст для всех участников этой большой рекламной платформы") for i in range(100)]
    result = build_signals(records)
    assert not result["edges"] and result["bounded_work"]["uninformative_lsh_bucket"] > 0
