import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
LINK = 750.0


def clusters(xy):
    if len(xy) == 1:
        return np.zeros(1, int)
    t = cKDTree(xy); p = np.array(list(t.query_pairs(LINK)))
    if len(p) == 0:
        return np.arange(len(xy))
    m = coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy)))
    return connected_components(m, directed=False)[1]
