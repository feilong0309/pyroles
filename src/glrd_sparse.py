__author__ = 'pratik'

import nimfa
import numpy as np
import cvxpy as cvx
from numpy import linalg
import argparse
import mdl

'''
V ~ GF is estimated using NMF for a factorization rank r.

where,
V = n * f, node-feature matrix
G = n * r, node-role matrix
F = r * f, role-feature matrix

'''


def get_residual(G, F, k):
    m, n = G.shape
    p, q = F.shape
    if n != p:
        raise ValueError('Incorrect dimensions for Matrix Factorization')
    R = np.zeros((m, q))
    for idx in xrange(n):
        if idx == k:
            continue
        R += np.outer(G[:, idx], F[idx, :])
    return R


def glrd_sparse(V, G, F, r, err_V, err_F):
    # sparsity threshold is num_nodes / num_roles
    for k in xrange(r):
        R = V - get_residual(G, F, k)  # compute residual

        # Solve for optimal G(.)(k) with sparsity constraints
        F_k = F[k, :]
        x_star_G = linalg.lstsq(R.T, F_k.T)[0].T
        x_G = cvx.Variable(x_star_G.shape[0])
        objective_G = cvx.Minimize(cvx.norm2(x_star_G - x_G))
        constraints_G = [x_G >= 0]
        constraints_G += [cvx.norm1(x_G) <= err_V]
        prob_G = cvx.Problem(objective_G, constraints_G)
        result = prob_G.solve(solver='SCS')
        if not np.isinf(result):
            G_k_min = np.asarray(x_G.value)
            G[:, k] = G_k_min[:, 0]
        else:
            print result

        # Solve for optimal F(k)(.) with sparsity constraints
        G_k = G[:, k]
        x_star_F = linalg.lstsq(R, G_k)[0]
        x_F = cvx.Variable(x_star_F.shape[0])
        objective_F = cvx.Minimize(cvx.norm2(x_star_F - x_F))
        constraints_F = [x_F >= 0]
        constraints_F += [cvx.sum_entries(x_F) <= err_F]
        prob_F = cvx.Problem(objective_F, constraints_F)
        result = prob_F.solve(solver='SCS')
        if not np.isinf(result):
            F_k_min = np.asarray(x_F.value)
            F[k, :] = F_k_min[0, :]
        else:
            print result

    return G, F


if __name__ == "__main__":
    np.random.seed(1001)
    argument_parser = argparse.ArgumentParser(prog='compute glrd')
    argument_parser.add_argument('-nf', '--node-feature', help='node-feature matrix file', required=True)
    argument_parser.add_argument('-o', '--output-prefix', help='glrd output prefix', required=True)
    argument_parser.add_argument('-od', '--output-dir', help='glrd output dir', required=True)

    args = argument_parser.parse_args()

    node_feature = args.node_feature
    out_prefix = args.output_prefix
    out_dir = args.output_dir

    refex_features = np.loadtxt(node_feature, delimiter=',')

    np.savetxt(out_dir + '/out-' + out_prefix + '-ids.txt', X=refex_features[:, 0])

    actual_fx_matrix = refex_features[:, 1:]
    n, f = actual_fx_matrix.shape
    print 'Number of Features: ', f
    print 'Number of Nodes: ', n

    number_bins = int(np.log2(n))
    max_roles = min([n, f])
    best_G = None
    best_F = None

    mdlo = mdl.MDL(number_bins)
    minimum_description_length = 1e20
    min_des_not_changed_counter = 0

    for rank in xrange(2, max_roles + 1):
        sparsity_threshold = float(n) / float(rank)
        lsnmf = nimfa.Lsnmf(actual_fx_matrix, rank=rank, max_iter=100)
        lsnmf_fit = lsnmf()
        # G = np.random.rand(n, rank)
        # F = np.random.rand(rank, f)
        G = np.asarray(lsnmf_fit.basis())
        F = np.asarray(lsnmf_fit.coef())

        G, F = glrd_sparse(V=actual_fx_matrix, G=G, F=F, r=rank, err_V=sparsity_threshold, err_F=sparsity_threshold)
        code_length_G = mdlo.get_huffman_code_length(G)
        code_length_F = mdlo.get_huffman_code_length(F)

        # For total bit length:
        # model_cost = code_length_W + code_length_H  # For total bit length
        # For avg. symbol bit length:
        model_cost = code_length_G * (G.shape[0] + G.shape[1]) + code_length_F * (F.shape[0] + F.shape[1])
        estimated_matrix = np.asarray(np.dot(G, F))
        loglikelihood = mdlo.get_log_likelihood(actual_fx_matrix, estimated_matrix)

        description_length = model_cost - loglikelihood

        if description_length < minimum_description_length:
            minimum_description_length = description_length
            best_G = np.copy(G)
            best_G[best_G <= 0.0] = 0.0
            best_F = np.copy(F)
            best_F[best_F <= 0.0] = 0.0
            min_des_not_changed_counter = 0
        else:
            min_des_not_changed_counter += 1
            if min_des_not_changed_counter == 10:
                break
        try:
            print 'Number of Roles: %s, Model Cost: %.2f, -loglikelihood: %.2f, Description Length: %.2f, MDL: %.2f (%s)' \
              % (rank, model_cost, loglikelihood, description_length, minimum_description_length, best_G.shape[1])
        except Exception:
            continue


    print 'MDL has not changed for these many iters:', min_des_not_changed_counter
    print '\nMDL: %.2f, Roles: %s' % (minimum_description_length, best_G.shape[1])
    np.savetxt(out_dir + '/' + 'out-' + out_prefix + "-nodeRoles.txt", X=best_G)
    np.savetxt(out_dir + '/' + 'out-' + out_prefix + "-roleFeatures.txt", X=best_F)
