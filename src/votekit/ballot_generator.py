from abc import abstractmethod
from pydantic import BaseModel
from typing import Optional
from .profile import PreferenceProfile
from .ballot import Ballot
from numpy.random import choice
import itertools as it
import random
import numpy as np

"""
IC
IAC
1d spatial
2d spatial
PL
BT
AC
Cambridge
"""


class Ballot_Generator(BaseModel):

    number_of_ballots: int
    candidate_list: list[set]
    ballot_length: Optional[int]  # = len(self.candidate_list)
    slate_to_candidate: Optional[dict]  # race: [candidate]
    pref_interval_by_slate: Optional[dict] = None  # race: {candidate : interval length}
    demo_breakdown: Optional[dict] = None  # race: percentage

    @abstractmethod
    def generate_ballots(self) -> PreferenceProfile:
        pass

    @staticmethod
    def cand_list_to_set(candidate_list):
        return [set(cand) for cand in candidate_list]

    @staticmethod
    def ballot_pool_to_profile(ballot_pool, candidate_list):
        ballot_weights = {}
        for ballot in ballot_pool:
            ballot_weights[tuple(ballot)] = ballot_weights.get(tuple(ballot), 0) + 1
        ballot_list = [
            Ballot(ranking=list(ranking), weight=weight)
            for ranking, weight in ballot_weights.items()
        ]
        return PreferenceProfile(ballots=ballot_list, candidates=candidate_list)


class IC(Ballot_Generator):
    def generate_ballots(self) -> PreferenceProfile:
        perm_set = it.permutations(self.candidate_list)
        #
        # Create a list of every perm [['A', 'B', 'C'], ['A', 'C', 'B'], ...]
        perm_rankings = [list(value) for value in perm_set]

        ballot_pool = []
        # TODO: why not just generate ballots from a uniform distribution like this
        #  ballot = list(choice(cand_list, ballot_length, p=cand_support_vec, replace=False))
        # instead of permutating all the candidates and then sampling

        for _ in range(self.number_of_ballots):
            index = random.randint(0, len(perm_rankings) - 1)
            ballot_pool.append(perm_rankings[index])

        return self.ballot_pool_to_profile(ballot_pool, self.candidate_list)


class IAC(Ballot_Generator):
    def generate_ballots(self) -> PreferenceProfile:
        perm_set = it.permutations(self.candidate_list)
        # Create a list of every perm [['A', 'B', 'C'], ['A', 'C', 'B'], ...]
        perm_rankings = [list(value) for value in perm_set]

        # IAC Process is equivalent to drawing from dirichlet dist with uniform parameters
        draw_probabilites = np.random.dirichlet([1] * len(perm_rankings))

        ballot_pool = []

        for _ in range(self.number_of_ballots):
            index = np.random.choice(range(6), 1, p=draw_probabilites)[0]
            ballot_pool.append(perm_rankings[index])

        return self.ballot_pool_to_profile(ballot_pool, self.candidate_list)


class PlackettLuce(Ballot_Generator):
    def __init__(
        self,
        *,
        number_of_ballots: int,
        candidate_list: list[set],
        ballot_length: Optional[int],
        candidate_to_slate: dict,
        pref_interval_by_race: dict,
        demo_breakdown: dict
    ):
        # TODO: can I override the signature like this?
        super().__init__(
            number_of_ballots=number_of_ballots,
            candidate_list=candidate_list,
            ballot_length=ballot_length,
            pref_interval_by_race=pref_interval_by_race,
            demo_breakdown=demo_breakdown,
            candidate_to_slate=candidate_to_slate,
        )

    def generate_ballots(self) -> PreferenceProfile:
        # if self.demo_breakdown is None:
        #     raise ValueError('demographic breakdown is needed for Plackett Luce')
        # if self.pref_interval_by_race is None:
        #     raise ValueError('preference interval by demographic is needed for Plackett Luce')

        # TODO: what to do with candidate_to_slate? add dirchlet sample option?s

        ballots_list = []

        for race in self.demo_breakdown.keys():
            # number of voters in this race/block
            num_ballots_race = int(self.number_of_ballots * self.demo_breakdown[race])
            pref_interval_dict = self.pref_interval_by_slate[race]
            # creates the interval of probabilities for candidates supported by this block
            cand_support_vec = [
                pref_interval_dict[cand] for cand in self.candidate_list
            ]

            for _ in range(num_ballots_race):
                ballot = list(
                    choice(
                        self.candidate_list,
                        self.ballot_length,
                        p=cand_support_vec,
                        replace=False,
                    )
                )
                ballots_list.append(ballot)

        pp = self.ballot_pool_to_profile(
            ballot_pool=ballots_list, candidate_list=self.candidate_list
        )
        return pp


class BradleyTerry(Ballot_Generator):
    def generate_ballots(self) -> PreferenceProfile:
        ...
        # n=len(self.candidate_list)
        # k=0
        # permutations = list(it.permutations(self.candidate_list))
        # for combo in permutations: ##computes (inverse of) the constant of proportionality
        #     m=1
        #     for i in range(n):
        #         for j in range(i+1,n):
        #             l=0
        #             for race in self.voter_proportion_by_race.keys():
        #                 l = l+self.voter_proportion_by_race[race]
        # *(self.cand_support_interval[race][combo[i]]
        # /(self.cand_support_interval[race][combo[i]]+self.cand_support_interval[race][combo[j]]))
        #             if j!=i:
        #                 m=m*l
        #     k=k+m
        # weights = []
        # for combo in permutations:
        #     prob=1
        #     for i in range(n):
        #         for j in range(i+1,n):
        #             l=0
        #     for race in self.voter_proportion_by_race.keys():
        #         l = l+self.voter_proportion_by_race[race]
        # *(self.cand_support_interval[race][combo[i]]
        # /( self.cand_support_interval[race][combo[i]]+self.cand_support_interval[race][combo[j]]))
        #     prob=prob*l
        #     weights.append(prob/k)##we're giving each permutation of cand_list a weight
        #     x = choice(range(len(permutations)), self.num_ballots, replace=True, p = weights)
        #     return list(permutations[i] for i in x)


class AlternatingCrossover(Ballot_Generator):
    def generate_ballots(self) -> PreferenceProfile:
        # assumes only two slates?
        ballots_list = []

        for slate in self.demo_breakdown.keys():
            num_ballots_race = int(self.number_of_ballots * self.demo_breakdown[slate])
            crossover_dict = self.slate_to_crossover_rate[slate]
            pref_interval_dict = self.pref_interval_by_slate[slate]

            for opposing_slate in crossover_dict.keys():
                crossover_rate = crossover_dict[opposing_slate]
                crossover_ballots = crossover_rate * num_ballots_race

                opposing_cands = self.slate_to_candidate[opposing_slate]
                bloc_cands = self.slate_to_candidate[slate]

                for _ in range(crossover_ballots):
                    pref_for_opposing = [
                        pref_interval_dict[cand] for cand in opposing_cands
                    ]
                    pref_for_bloc = [pref_interval_dict[cand] for cand in bloc_cands]

                    bloc_cands = list(
                        choice(self.candidate_list, p=pref_for_bloc, replace=False)
                    )
                    opposing_cands = list(
                        choice(self.candidate_list, p=pref_for_opposing, replace=False)
                    )

                    ballot = bloc_cands
                    if slate != opposing_slate:  # alternate
                        ballot = [
                            item
                            for sublist in zip(opposing_cands, bloc_cands)
                            for item in sublist
                        ]

                    # check that ballot_length is shorter than total number of cands
                    ballot = ballot[: self.ballot_length]
                    ballots_list.append(ballot)

        pp = self.ballot_pool_to_profile(
            ballot_pool=ballots_list, candidate_list=self.candidate_list
        )
        return pp


class CambridgeSampler(Ballot_Generator):
    def generate_ballots(self) -> PreferenceProfile:
        pass


class OneDimSpatial(Ballot_Generator):
    def generate_ballots(self) -> PreferenceProfile:
        candidate_position_dict = {
            c: np.random.normal(1, 0, len(self.candidate_list))
            for c in self.candidate_list
        }
        voter_positions = np.random.normal(1, 0, self.number_of_ballots)

        ballot_pool = []

        for vp in voter_positions:
            distance_dict = {
                c: abs(v - vp) for c, v, in candidate_position_dict.items()
            }
            candidate_order = sorted(distance_dict, key=distance_dict.get)
            ballot_pool.append(candidate_order)

        return self.ballot_pool_to_profile(ballot_pool)


# class TwoDimSpatial(Ballot_Generator):
#     @override
#     def generate_ballots() -> PreferenceProfile:
#         pass
