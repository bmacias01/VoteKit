from .ballot import Ballot
from typing import Optional
from pydantic import BaseModel, validator
import pandas as pd


class PreferenceProfile(BaseModel):
    """
    Data structure to represent a preference profile, a collection of cast ballots.
    :param ballots: :class:`list[Ballot]` list of Ballot objects
    :param candidates: :class:`list` of candidates, can be user defined
    """

    ballots: list[Ballot]
    candidates: Optional[list] = None
    df: pd.DataFrame = pd.DataFrame()

    @validator("candidates")
    def cands_must_be_unique(cls, candidates: list) -> list:
        if not len(set(candidates)) == len(candidates):
            raise ValueError("all candidates must be unique")
        return candidates

    def get_ballots(self) -> list[Ballot]:
        """
        Returns list of ballots
        :rtype: :class:`list[Ballots]`
        """
        return self.ballots

    # @cache
    def get_candidates(self) -> list:
        """
        Returns list of unique candidates
        :rtype: :class:`list`
        """
        if self.candidates is not None:
            return self.candidates

        unique_cands: set = set()
        for ballot in self.ballots:
            unique_cands.update(*ballot.ranking)

        return list(unique_cands)

    # can also cache
    def num_ballots(self):
        """
        Returns the total number of case ballots.
        Assumes weights correspond to number of ballots given to a ranking
        :rtype: :class:`Fraction`
        """
        num_ballots = 0
        for ballot in self.ballots:
            num_ballots += ballot.weight

        return num_ballots

    def to_dict(self, standardize: bool) -> dict:
        """
        Converts preference profile to dictionary.
        Keys: ballot ranking as a string tupple.
        Values: ballot weights.
        :param standardize: :class:`bool` Normalizes weights to sum to one.
        :return: a dictionary representation of a perference profile
        :rtype: :class:`dict`
        """
        num_ballots = self.num_ballots()
        di: dict = {}
        for ballot in self.ballots:
            rank_tuple = tuple(next(iter(item)) for item in ballot.ranking)
            # print(rank_tuple)
            if rank_tuple not in di.keys():
                if standardize:
                    di[rank_tuple] = ballot.weight / num_ballots
                else:
                    di[rank_tuple] = ballot.weight

            else:
                if standardize:
                    di[rank_tuple] += ballot.weight / num_ballots
                else:
                    di[rank_tuple] += ballot.weight
        return di

    class Config:
        arbitrary_types_allowed = True

    def create_df(self) -> pd.DataFrame:
        """
        Creates a `DataFrame` for display and building plots
        :rtype: :class:`DataFrame`
        """
        weights = []
        ballots = []
        for ballot in self.ballots:
            part = []
            for ranking in ballot.ranking:
                for cand in ranking:
                    if len(ranking) > 2:
                        part.append(f"{cand} (Tie)")
                    else:
                        part.append(cand)
            ballots.append(tuple(part))
            weights.append(int(ballot.weight))

        df = pd.DataFrame({"Ballots": ballots, "Weight": weights})
        # df["Ballots"] = df["Ballots"].astype(str).str.ljust(60)
        df["Voter Share"] = df["Weight"] / df["Weight"].sum()
        # fill nans with zero for edge cases
        df["Voter Share"] = df["Voter Share"].fillna(0.0)
        # df["Weight"] = df["Weight"].astype(str).str.rjust(3)
        return df.reset_index(drop=True)

    def head(self, n: int, percents: Optional[bool] = False) -> pd.DataFrame:
        """
        Displays top-n ballots in profile based on weight.
        :param n: :class:`int` top n candidates
        :param percents: optional :class:`bool` use `True` to also display 'voter share'
        :return: a :class:`DataFrame`
        :rtype: :class:`DataFrame`
        """
        if self.df.empty:
            self.df = self.create_df()

        df = self.df.sort_values(by="Weight", ascending=False)
        if not percents:
            return df.drop(columns="Voter Share").head(n).reset_index(drop=True)

        return df.head(n).reset_index(drop=True)

    def tail(self, n: int, percents: Optional[bool] = False) -> pd.DataFrame:
        """
        Displays bottom-n ballots in profile based on weight
        :param n: :class:`int` bottom n candidates
        :param percents: optional :class:`bool` use `True` to also display 'voter share'
        :return: a :class:`DataFrame`
        :rtype: :class:`DataFrame`
        """
        if self.df.empty:
            self.df = self.create_df()

        df = self.df.sort_values(by="Weight", ascending=True)
        if not percents:
            return df.drop(columns="Voter Share").head(n).reset_index(drop=True)

        return df.head(n).reset_index(drop=True)

    def __str__(self) -> str:
        """
        Displays top 15 or whole profiles
        :rtype: :class:`str`
        """
        if self.df.empty:
            self.dff = self.create_df()

        if len(self.df) < 15:
            return self.head(n=len(self.df)).to_string(index=False, justify="justify")

        return self.head(n=15).to_string(index=False, justify="justify")

    # set repr to print outputs
    __repr__ = __str__
