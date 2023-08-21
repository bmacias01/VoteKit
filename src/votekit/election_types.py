from .profile import PreferenceProfile
from .ballot import Ballot
from .election_state import ElectionState
from typing import Callable, Optional
import random
from fractions import Fraction
from copy import deepcopy
from collections import namedtuple


class STV:
    """
    Class to run single-winner IRV and multi-winner STV elections.
    """

    def __init__(
        self,
        profile: PreferenceProfile,
        transfer: Callable,
        seats: int,
        quota: str = "droop",
    ):
        """
        :param profile: :class:`PreferenceProfile`: initial perference profile
        :param transfer: (function): vote transfer method such as fractional transfer
        :param seats: :class:`int`: number of winners/size of committee
        """
        self.__profile = profile
        self.transfer = transfer
        self.seats = seats
        self.election_state = ElectionState(
            curr_round=0,
            elected=[],
            eliminated=[],
            remaining=[
                cand
                for cand, votes in compute_votes(
                    profile.get_candidates(), profile.get_ballots()
                )
            ],
            profile=profile,
        )
        self.threshold = self.get_threshold(quota)

    # can cache since it will not change throughout rounds
    def get_threshold(self, quota: str) -> int:
        quota = quota.lower()
        if quota == "droop":
            return int(self.__profile.num_ballots() / (self.seats + 1) + 1)
        elif quota == "hare":
            return int(self.__profile.num_ballots() / self.seats)
        else:
            raise ValueError("Misspelled or unknown quota type")

    def next_round(self) -> bool:
        """
        Determines if the number of seats has been met to call election
        :rtype: :class:`bool`
        """
        return len(self.election_state.get_all_winners()) != self.seats

    def run_step(self) -> ElectionState:
        """
        Simulates one round an STV election
        :return: an updated ElectionState
        :rtype: :class:`ElectionState`
        """
        ##TODO:must change the way we pass winner_votes
        remaining: list[str] = self.election_state.remaining
        ballots: list[Ballot] = self.election_state.profile.get_ballots()
        fp_votes = compute_votes(remaining, ballots)  ##fp means first place
        elected = []
        eliminated = []

        # if number of remaining candidates equals number of remaining seats,
        # everyone is elected
        if len(remaining) == self.seats - len(self.election_state.get_all_winners()):
            elected = [cand for cand, votes in fp_votes]
            remaining = []
            ballots = []
            # TODO: sort remaining candidates by vote share

        # elect all candidates who crossed threshold
        elif fp_votes[0].votes >= self.threshold:
            for candidate, votes in fp_votes:
                if votes >= self.threshold:
                    elected.append(candidate)
                    remaining.remove(candidate)
                    ballots = self.transfer(
                        candidate,
                        ballots,
                        {cand: votes for cand, votes in fp_votes},
                        self.threshold,
                    )
        # since no one has crossed threshold, eliminate one of the people
        # with least first place votes
        elif self.next_round():
            lp_votes = min([votes for cand, votes in fp_votes])
            lp_candidates = [
                candidate for candidate, votes in fp_votes if votes == lp_votes
            ]
            # is this how to break ties, can be different based on locality
            lp_cand = random.choice(lp_candidates)
            eliminated.append(lp_cand)
            ballots = remove_cand(lp_cand, ballots)
            remaining.remove(lp_cand)

        self.election_state = ElectionState(
            curr_round=self.election_state.curr_round + 1,
            elected=elected,
            eliminated=eliminated,
            remaining=remaining,
            profile=PreferenceProfile(ballots=ballots),
            previous=self.election_state,
        )
        return self.election_state

    def run_election(self) -> ElectionState:
        """
        Runs complete STV election
        :return: The outcome of an STV election
        :rtype: :class:`ElectionState`
        """
        if not self.next_round():
            raise ValueError(
                f"Length of elected set equal to number of seats ({self.seats})"
            )

        while self.next_round():
            self.run_step()

        return self.election_state

    def get_init_profile(self):
        "returns the initial profile of the election"
        return self.__profile


class SequentialRCV:
    """
    Class to run a Sequential RCV election
    """

    def __init__(self, profile: PreferenceProfile, seats: int):
        """
        :param profile: :class:`PreferenceProfile`
        :param seats: :class:`int`: number of winners/size of committee
        """
        self.seats = seats
        self.profile = profile
        self.election_state = ElectionState(
            curr_round=0,
            elected=[],
            eliminated=[],
            remaining=[],
            profile=profile,
        )

    def run_step(self, old_profile: PreferenceProfile) -> ElectionState:
        """
        Simulates a single step of the sequential RCV contest
        which is a full IRV election run on the current set of candidates
        :return: an updated ElectionState
        :rtype: :class:`ElectionState`
        """
        old_election_state = self.election_state

        IRVrun = STV(old_profile, transfer=seqRCV_transfer, seats=1)
        old_election = IRVrun.run_election()
        elected_cand = old_election.get_all_winners()[0]

        # Removes elected candidate from Ballot List
        updated_ballots = remove_cand(elected_cand, old_profile.get_ballots())

        # Updates profile with removed candidates
        updated_profile = PreferenceProfile(ballots=updated_ballots)

        self.election_state = ElectionState(
            curr_round=old_election_state.curr_round + 1,
            elected=list(elected_cand),
            profile=updated_profile,
            previous=old_election_state,
            remaining=old_election.remaining,
        )
        return self.election_state

    def run_election(self) -> ElectionState:
        """
        Simulates a complete sequential RCV contest.
        Will run rounds of elections until elected seats fill
        :return: The outcome of a Sequential RCV election
        :rtype: :class:`ElectionState`
        """
        old_profile = self.profile
        elected = []  # type:ignore
        seqRCV_step = self.election_state

        while len(elected) < self.seats:
            seqRCV_step = self.run_step(old_profile)
            elected.append(seqRCV_step.elected)
            old_profile = seqRCV_step.profile
        return seqRCV_step


class Borda:
    """
    Class to run a Borda Election
    """

    def __init__(
        self,
        profile: PreferenceProfile,
        seats: int,
        borda_weights: Optional[list] = None,
        standard: bool = True,
    ):
        """
        :param profile: :class:`PreferenceProfile`: election as a perference profile object\n
        :param seats: :class:`int`: number of winners/size of committee \n
        :param borda_weights: :class:`list[int]` Weights given to each ranked vote. If empty,
        defaults weights are assigned which, for n-candidates, gives first places votes
        n-points, second place votes n-1 points, third place votes n-2 votes,..., last place
        votes get 1 point.
        :param standard: Defaults to `True`, runs a standard Borda election.
        Cast a short ballot points are fractionally distributed to remaining candidates
        """
        self.state = ElectionState(
            curr_round=0,
            elected=[],
            eliminated=[],
            remaining=[],
            profile=profile,
            previous=None,
        )
        self.seats = seats

        self.num_cands = len(self.state.profile.get_candidates())

        if borda_weights is None:
            self.borda_weights = [i for i in range(self.num_cands, 0, -1)]
        else:
            self.borda_weights = borda_weights

        self.standard = standard

    def run_borda_step(self) -> ElectionState:
        """
        Simulates a full Borda election.
        :return: Outcome of a Borda Election
        :rtype: :class:`ElectionState`
        """
        borda_scores = {}  # {candidate : int borda_score}
        candidates_ballots = {}  # type:ignore
        all_candidates = self.state.profile.get_candidates()

        # Populates dicts: candidate_rank_freq, candidates_ballots
        for ballot in self.state.profile.get_ballots():
            frequency = ballot.weight
            rank = 0
            for candidate in ballot.ranking:
                candidate = str(candidate)  # type:ignore
                if candidate not in candidates_ballots:
                    candidates_ballots[candidate] = []
                candidates_ballots[candidate].append(
                    ballot
                )  # adds ballot where candidate was ranked

                # adds Borda score to candidate
                if candidate not in borda_scores:
                    borda_scores[candidate] = 0
                if (rank + 1) <= len(self.borda_weights):
                    borda_scores[candidate] += (
                        frequency * self.borda_weights[rank]
                    )  # type:ignore

                rank += 1

            if self.standard is True:
                if rank < (len(self.borda_weights) + 1):
                    # X find total remaining borda points
                    remaining_points = sum(self.borda_weights[rank:])

                    # Y find unranked candidates by the ballot

                    ballot_ranking = [
                        item for subset in ballot.ranking for item in subset
                    ]
                    remaining_cands = list(set(all_candidates) - set(ballot_ranking))

                    # borda_scores[all remaining candidates] = X / Y
                    for candidate in remaining_cands:
                        candidate = str(set(candidate))  # type:ignore
                        if candidate not in borda_scores:
                            borda_scores[candidate] = frequency * (  # type:ignore
                                remaining_points / len(remaining_cands)
                            )
                        else:
                            borda_scores[candidate] += frequency * (  # type:ignore
                                remaining_points / len(remaining_cands)
                            )

        # Identifies Borda winners (elected) and losers (eliminated)
        sorted_borda = sorted(borda_scores, key=borda_scores.get, reverse=True)
        winners = sorted_borda[: self.seats]
        losers = sorted_borda[self.seats :]

        # reformat winners and losers to be compatible with election types winners/losers list
        winners_list = [cand.replace("{'", "").replace("'}", "") for cand in winners]
        losers_list = [cand.replace("{'", "").replace("'}", "") for cand in losers]

        # Create winner_votes dict for ElectionState object
        winner_ballots = {}
        for candidate in winners:
            winner_ballots[candidate] = candidates_ballots[candidate]

        # New final state object
        self.state = ElectionState(
            elected=winners_list,
            eliminated=losers_list,
            remaining=[],
            profile=self.state.profile,
            curr_round=(self.state.curr_round + 1),
            previous=self.state,
        )
        return self.state

    def run_borda_election(self) -> ElectionState:
        """
        Function will also run a full borda election
        :rtype: :class:`ElectionType`
        """
        final_state = self.run_borda_step()
        return final_state


## Election Helper Functions
CandidateVotes = namedtuple("CandidateVotes", ["cand", "votes"])


def compute_votes(candidates: list, ballots: list[Ballot]) -> list[CandidateVotes]:
    """
    Computes first place votes for all candidates in a preference profile
    :param candidates: :class:`list` of candidates
    :param ballots: list of :class:`Ballot` objects
    :returns: list of number of votes for each candidate
    """
    votes = {}
    for candidate in candidates:
        weight = Fraction(0)
        for ballot in ballots:
            if ballot.ranking and ballot.ranking[0] == {candidate}:
                weight += ballot.weight
        votes[candidate] = weight

    ordered = [
        CandidateVotes(cand=key, votes=value)
        for key, value in sorted(votes.items(), key=lambda x: x[1], reverse=True)
    ]

    return ordered


def fractional_transfer(
    winner: str, ballots: list[Ballot], votes: dict, threshold: int
) -> list[Ballot]:
    """
    Calculates fractional transfer from winner, then removes winner
    from the list of ballots
    """
    transfer_value = (votes[winner] - threshold) / votes[winner]

    for ballot in ballots:
        if ballot.ranking and ballot.ranking[0] == {winner}:
            ballot.weight = ballot.weight * transfer_value

    return remove_cand(winner, ballots)


def random_transfer(
    winner: str, ballots: list[Ballot], votes: dict, threshold: int
) -> list[Ballot]:
    """
    Cambridge/Cincinnati-style transfer where transfer ballots are selected randomly
    """

    # turn all of winner's ballots into (multiple) ballots of weight 1
    weight_1_ballots = []
    for ballot in ballots:
        if ballot.ranking and ballot.ranking[0] == {winner}:
            # note: under random transfer, weights should always be integers
            for _ in range(int(ballot.weight)):
                weight_1_ballots.append(
                    Ballot(
                        id=ballot.id,
                        ranking=ballot.ranking,
                        weight=Fraction(1),
                        voters=ballot.voters,
                    )
                )

    # remove winner's ballots
    ballots = [
        ballot
        for ballot in ballots
        if not (ballot.ranking and ballot.ranking[0] == {winner})
    ]

    surplus_ballots = random.sample(weight_1_ballots, int(votes[winner]) - threshold)
    ballots += surplus_ballots

    transfered = remove_cand(winner, ballots)

    return transfered


def seqRCV_transfer(
    winner: str, ballots: list[Ballot], votes: dict, threshold: int
) -> list[Ballot]:
    """
    Useful for a Sequential RCV election which does not use a transfer method ballots \n
    :param ballots: list of ballots \n
    :return: same ballot list
    """
    return ballots


def remove_cand(removed_cand: str, ballots: list[Ballot]) -> list[Ballot]:
    """
    Removes candidate from ranking of the ballots
    :param removed_cand: :class:`str`: Removes this candidate from ballots
    :param ballots: list of :class:`Ballot` objects
    :returns: Updated ballot list
    """
    update = deepcopy(ballots)

    for n, ballot in enumerate(update):
        new_ranking = [
            candidate for candidate in ballot.ranking if candidate != {removed_cand}
        ]
        update[n].ranking = new_ranking

    return update
