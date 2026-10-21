"""A10a texture: GLCM statistics must match a direct per-window computation (D-023)."""
import numpy as np
from care_ew.texture import glcm, local_sd


def _direct(q, r, c, w=7, L=8):
    h = w // 2
    P = np.zeros((L, L))
    for dr, dc in ((0, 1), (1, 0)):
        for i in range(r - h, r + h + 1):
            for j in range(c - h, c + h + 1):
                if 0 <= i < q.shape[0] and 0 <= j < q.shape[1] and i + dr < q.shape[0] and j + dc < q.shape[1]:
                    a, b = q[i, j], q[i + dr, j + dc]
                    if a >= 0 and b >= 0:
                        P[a, b] += 1; P[b, a] += 1
    p = P / P.sum()
    I, J = np.indices((L, L))
    mu = (p * I).sum(); var = (p * (I - mu) ** 2).sum()
    return dict(con=(p * (I - J) ** 2).sum(), hom=(p / (1 + (I - J) ** 2)).sum(),
                ent=-(p[p > 0] * np.log(p[p > 0])).sum(), cor=(p * (I - mu) * (J - mu)).sum() / var)


def test_glcm_matches_direct():
    rng = np.random.default_rng(0)
    q = rng.integers(0, 8, (30, 30)).astype(np.int8)
    q[5:9, 5:9] = -1                                    # missing pixels are skipped
    con, hom, ent, cor = glcm(q)
    for r, c in ((15, 15), (7, 10), (20, 3)):
        d = _direct(q, r, c)
        assert np.allclose([con[r, c], hom[r, c], ent[r, c], cor[r, c]], [d["con"], d["hom"], d["ent"], d["cor"]], atol=1e-6)


def test_texture_contrast_orders_patterns():
    smooth = np.zeros((20, 20), np.int8); smooth[:, 10:] = 7
    checker = (np.indices((20, 20)).sum(0) % 2 * 7).astype(np.int8)
    assert glcm(checker)[0][10, 4] > glcm(smooth)[0][10, 4]       # contrast
    assert glcm(checker)[1][10, 4] < glcm(smooth)[1][10, 4]       # homogeneity


def test_local_sd():
    x = np.random.default_rng(1).normal(size=(40, 40))
    sd = local_sd(x, 5)
    assert abs(sd[20, 20] - x[18:23, 18:23].std()) < 1e-9
