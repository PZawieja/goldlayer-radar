import pyarrow as pa
import pyarrow.parquet as pq

from radar.common import DATA
from radar.llm import CLASSIFIED_SCHEMA, CLUSTER_SCHEMA


def main():
    out = DATA / "classified"
    out.mkdir(parents=True, exist_ok=True)
    targets = {
        out / "items_0000-00-00.parquet": CLASSIFIED_SCHEMA,
        out / "clusters.parquet": CLUSTER_SCHEMA,
    }
    for path, schema in targets.items():
        if not path.exists():
            pq.write_table(pa.Table.from_pylist([], schema=schema), path)
            print(f"created {path.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main()
