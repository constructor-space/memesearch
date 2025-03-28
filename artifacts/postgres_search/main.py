import json
import time
from pathlib import Path
from typing import Literal, Type

from models import get_models
from pydantic import BaseModel
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.orm import Session, DeclarativeBase
from testcontainers.postgres import PostgresContainer

ROOT_DIR = Path(__file__).parent


class QueryResults(BaseModel):
    query: str
    results: list[tuple[float, str]]


class OperatorResults(BaseModel):
    time: float
    query_count: int
    queries: list[QueryResults]


def run_search_for(
    session: Session,
    Data: Type[DeclarativeBase],
    operator: Literal['<->', '<->>', '<->>>'],
) -> OperatorResults:
    t = time.perf_counter()
    qres = []
    query_count = 0
    queries = [
        'папей чай с мятай',
        'чай с мятой',
        'мама сказала мясо',
        'может упасть крест',
        'меня никто не понимает',
    ]
    for query in queries:
        for _ in range(10):
            dist = Data.text.op(operator)(query).label('dist')
            q = select(dist, Data.name).where(dist < 0.7).order_by(dist)
            results = [(dist, name) for (dist, name) in session.execute(q).all()]
        query_count += 10
        qres.append(QueryResults(query=query, results=results))
    return OperatorResults(
        time=time.perf_counter() - t, query_count=query_count, queries=qres
    )


class IndexResults(BaseModel):
    index_type: str
    creation: float
    operators: dict[str, OperatorResults]


def run_test_for(index_type: Literal['gin', 'gist']) -> None:
    data = json.loads((ROOT_DIR / 'data.json').read_text())

    with PostgresContainer('postgres:17') as postgres:
        psql_url = postgres.get_connection_url()
        engine = create_engine(psql_url)
        Base, Data = get_models(index_type)
        with Session(engine) as session, session.begin():
            session.execute(text('create extension pg_trgm'))
        Base.metadata.create_all(engine)
        t = time.perf_counter()
        with Session(engine) as session, session.begin():
            session.execute(insert(Data.__table__), data)
        creation = time.perf_counter() - t
        operators = {}
        for operator in ('<->', '<->>', '<->>>'):
            with Session(engine) as session, session.begin():
                operators[operator] = run_search_for(session, Data, operator)
        results = IndexResults(
            index_type=index_type, creation=creation, operators=operators
        )
        (ROOT_DIR / f'{index_type}.json').write_text(results.model_dump_json(indent=2))


def main():
    for index_type in ('gin', 'gist'):
        run_test_for(index_type)


if __name__ == '__main__':
    main()
