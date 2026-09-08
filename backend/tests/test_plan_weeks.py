from app.domain.plan import sparse_weeks


def test_sparse_weeks_omite_ceros():
    targets = {("123", 5): 3, ("123", 12): 0, ("123", 40): 7, ("999", 1): 2}
    assert sparse_weeks(targets, "123") == {"5": 3, "40": 7}
    assert sparse_weeks(targets, "999") == {"1": 2}
    assert sparse_weeks(targets, "000") == {}
