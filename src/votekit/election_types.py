from votekit.profile import PreferenceProfile
from votekit.ballot import Ballot
from votekit.models import Outcome
from typing import Callable
import random
from fractions import Fraction


class STV:
    def __init__(self, profile: PreferenceProfile, transfer: Callable, seats: int):
        self.profile = profile
        self.transfer = transfer
        self.elected: set = set()
        self.eliminated: set = set()
        self.seats = seats
        self.threshold = self.get_threshold()

    # can cache since it will not change throughout rounds
    def get_threshold(self) -> int:
        """
        Droop qouta
        """
        return int(self.profile.num_ballots() / (self.seats + 1) + 1)

    # change name of this function and reverse bool
    def is_complete(self) -> bool:
        """
        Determines if the number of seats has been met to call election
        """
        return len(self.elected) == self.seats

    def run_step(self, profile: PreferenceProfile) -> tuple[PreferenceProfile, Outcome]:
        """
        Simulates one round an STV election
        """
        candidates: list = profile.get_candidates()
        ballots: list = profile.get_ballots()
        fp_votes: dict = compute_votes(candidates, ballots)

        # print('ballots', type(ballots))
        # print('candidates', type(candidates))

        # if number of remaining candidates equals number of remaining seats
        if len(candidates) == self.seats - len(self.elected):
            # TODO: sort remaing candidates by vote share
            self.elected.update(set(candidates))
            return profile, Outcome(
                elected=self.elected,
                eliminated=self.eliminated,
                remaining=set(candidates),
                votes=fp_votes,
            )

        for candidate in candidates:
            if fp_votes[candidate] >= self.threshold:
                self.elected.add(candidate)
                candidates.remove(candidate)
                ballots = self.transfer(candidate, ballots, fp_votes, self.threshold)

        if not self.is_complete():
            lp_votes = min(fp_votes.values())
            lp_candidates = [
                candidate for candidate, votes in fp_votes.items() if votes == lp_votes
            ]
            # is this how to break ties, can be different based on locality
            lp_cand = random.choice(lp_candidates)
            ballots = remove_cand(lp_cand, ballots)
            candidates.remove(lp_cand)
            # print("loser", lp_cand)
            self.eliminated.add(lp_cand)

        return PreferenceProfile(ballots=ballots), Outcome(
            elected=self.elected,
            eliminated=self.eliminated,
            remaining=set(candidates),
            votes=fp_votes,
        )


# TO:DO update election to modified election_state class
class SequentialRCV:
    def __init__(self, profile: PreferenceProfile, seats: int):
        self.profile = profile
        self.seats = seats
        self.elected: set = set()
        self.outcome = Outcome(
            elected=[],
            eliminated=[],
            remaining=[],
            profile=self.profile,
            winner_vote=None,
            previous=None,
        )

    def run_seqRCV_step(self, old_profile: PreferenceProfile):
        """
        Simulates a single step of the sequential RCV contest
        """
        singleSTVrun = STV(old_profile, transfer=seqRCV_transfer, seats=1)
        runOutcome = singleSTVrun.run_step(old_profile)[1]
        elected_cand = runOutcome.elected
        for ele in elected_cand:
            elected_cand = ele

        # Removes elected candidate from Ballot List
        updated_ballots = remove_cand(elected_cand, old_profile.get_ballots())

        # Updates profile with removed candidates
        updated_profile = PreferenceProfile(ballots=updated_ballots)

        return updated_profile, runOutcome

    def run_seqRCV_election(self):
        """
        Simulates a complete sequential RCV contest
        """
        elected_cands = set()
        eliminated_cands = set()
        old_profile = self.profile
        outcomes = []
        while len(elected_cands) < self.seats:
            step_result = self.run_seqRCV_step(old_profile)
            updated_profile = step_result[0]
            outcomes.append(step_result[1])
            elected_cands.add(str(step_result[1].elected))
            eliminated_cands.add(str(step_result[1].eliminated))
            old_profile = updated_profile

        if elected_cands == {"set()"}:
            elected_cands = set()
        else:
            elected_cands = {element.strip("{'}") for element in elected_cands}
            elected_cands = set(elected_cands)
        if eliminated_cands == {"set()"}:
            eliminated_cands = set()
        else:
            eliminated_cands = {element.strip("{'}") for element in eliminated_cands}
            eliminated_cands = set(eliminated_cands)

        final_outcome = Outcome(
            elected=elected_cands,
            eliminated=eliminated_cands,
            remaining=step_result[1].remaining,
            votes=None,  # Andrew: scary idk what to do here yet
        )

        return final_outcome


class Borda:
    def __init__(self, profile: PreferenceProfile, seats: int, borda_weights: list):
        self.profile = profile
        self.borda_weights = borda_weights
        self.seats = seats

    def run_borda_step(self):
        """
        Simulates a complete Borda election
        """

        borda_scores = {}  # {candidate : int borda_score}
        candidate_rank_freq = (
            {}
        )  # {candidate : [1st rank total, 2nd rank total,..., n rank total]}
        candidates_ballots = {}  # {candidate : [ballots mentioning candidate]}

        for ballot in self.profile.get_ballots():
            frequency = ballot.weight
            index = 0
            for candidate in ballot.ranking:
                candidate = str(candidate)

                if candidate not in candidate_rank_freq:
                    candidate_rank_freq[candidate] = [
                        0 for _ in range(len(ballot.ranking))
                    ]
                    candidate_rank_freq[candidate][index] = frequency
                else:
                    candidate_rank_freq[candidate][index] += frequency
                if candidate not in candidates_ballots:
                    candidates_ballots[candidate] = []
                    candidates_ballots[candidate].append(ballot)
                else:
                    candidates_ballots[candidate].append(ballot)
                index += 1

        for key in candidate_rank_freq:
            borda_scores[key] = sum(
                [x * y for x, y in zip(candidate_rank_freq[key], self.borda_weights)]
            )

        sorted_borda = sorted(borda_scores, key=borda_scores.get, reverse=True)

        winners = sorted_borda[: self.seats]

        # TO-DO: Adjust Outcome class to new args
        winner_votes = {}
        for winner in winners:
            winner_votes[winner] = candidates_ballots[winner]

        elected_cands = set(winners)
        eliminated_cands = set(sorted_borda[self.seats :])
        if elected_cands == {"set()"}:
            elected_cands = set()
        else:
            elected_cands = {element.strip("{'}") for element in elected_cands}
            elected_cands = set(elected_cands)
        if eliminated_cands == {"set()"}:
            eliminated_cands = set()
        else:
            eliminated_cands = {element.strip("{'}") for element in eliminated_cands}
            eliminated_cands = set(eliminated_cands)

        return PreferenceProfile(ballots=self.profile.get_ballots()), Outcome(
            remaining=set(),
            elected=elected_cands,
            eliminated=eliminated_cands,
        )

        # return PreferenceProfile(ballots=profile.get_ballots(), Outcome(
        #     curr_round=1,
        #     elected=winners,
        #     eliminated=sorted_borda[seats:],
        #     remaining=[],
        #     profile=profile,
        #     winner_votes=winner_votes,
        #     previous=None
        # )

    def run_borda_election(self):
        profile, outcome = self.run_borda_step()
        return outcome


def compute_votes(candidates: list, ballots: list[Ballot]) -> dict:
    """
    Computes first place votes for all candidates in a preference profile
    """
    votes = {}

    for candidate in candidates:
        weight = Fraction(0)
        for ballot in ballots:
            if ballot.ranking and ballot.ranking[0] == {candidate}:
                weight += ballot.weight
        votes[candidate] = weight

    return votes


def fractional_transfer(
    winner: str, ballots: list[Ballot], votes: dict, threshold: int
) -> list[Ballot]:
    # find the transfer value, add tranfer value to weights of vballots
    # that listed the elected in first place, remove that cand and shift
    # everything up, recomputing first-place votes
    transfer_value = (votes[winner] - threshold) / votes[winner]

    for ballot in ballots:
        if ballot.ranking and ballot.ranking[0] == {winner}:
            ballot.weight = ballot.weight * transfer_value

    transfered = remove_cand(winner, ballots)

    return transfered


def seqRCV_transfer(
    winner: str, ballots: list[Ballot], votes: dict, threshold: int
) -> list[Ballot]:
    """
    Doesn't transfer votes, useful for Sequential RCV election
    """
    return ballots


def remove_cand(removed_cand: str, ballots: list[Ballot]) -> list[Ballot]:
    """
    Removes candidate from ranking of the ballots
    """
    for n, ballot in enumerate(ballots):
        new_ranking = []
        for candidate in ballot.ranking:
            if candidate != {removed_cand}:
                new_ranking.append(candidate)
        ballots[n].ranking = new_ranking

    return ballots
