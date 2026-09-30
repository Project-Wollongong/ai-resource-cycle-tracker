"""Export the local tracker SQLite database to a customer-friendly workbook."""

from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB_FILE = ROOT / "data" / "tracker.db"
OUTPUT_FILE = ROOT / "data" / "抓取数据展示.xlsx"

QUERIES = {
    "股票池": """
        SELECT code, name, commodity, stage, active
        FROM stocks
        ORDER BY code
    """,
    "股票行情": """
        SELECT s.code, p.date, p.open, p.high, p.low, p.close, p.volume
        FROM price_bars p
        JOIN stocks s ON s.id = p.stock_id
        ORDER BY p.date DESC, s.code
    """,
    "公司公告": """
        SELECT s.code, a.ann_date, a.headline, a.ann_type, a.type_score,
               a.price_sensitive, a.url, a.ai_summary
        FROM announcements a
        JOIN stocks s ON s.id = a.stock_id
        ORDER BY a.ann_date DESC
    """,
    "商品行情": """
        SELECT instrument, date, close
        FROM commodity_bars
        ORDER BY date DESC, instrument
    """,
    "评分结果": """
        SELECT s.code, sc.date, sc.cycle_score, sc.label,
               sc.announcement_score, sc.resource_score,
               sc.commodity_score, sc.risk_score, sc.sentiment_score
        FROM score_snapshots sc
        JOIN stocks s ON s.id = sc.stock_id
        ORDER BY sc.date DESC, sc.cycle_score DESC
    """,
    "信号记录": """
        SELECT s.code, sg.date, sg.signal_type, sg.source, sg.label,
               sg.reason, sg.price_at_signal, sg.cycle_score_at_signal
        FROM signals sg
        JOIN stocks s ON s.id = sg.stock_id
        ORDER BY sg.date DESC
    """,
    "抓取运行记录": """
        SELECT id, run_at, finished_at, trigger, status, stats_json
        FROM pipeline_runs
        ORDER BY run_at DESC
    """,
}


def main() -> None:
    if not DB_FILE.exists():
        raise FileNotFoundError(f"数据库不存在：{DB_FILE}")

    with sqlite3.connect(DB_FILE) as connection:
        tables = {
            sheet_name: pd.read_sql_query(query, connection)
            for sheet_name, query in QUERIES.items()
        }
        overview = pd.DataFrame(
            [
                {"数据类型": sheet_name, "记录数量": len(data)}
                for sheet_name, data in tables.items()
            ]
        )

        with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
            overview.to_excel(writer, sheet_name="数据概览", index=False)
            for sheet_name, data in tables.items():
                data.to_excel(writer, sheet_name=sheet_name, index=False)

            for worksheet in writer.book.worksheets:
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions
                for column in worksheet.columns:
                    width = min(
                        max(len(str(cell.value or "")) for cell in column) + 2,
                        50,
                    )
                    worksheet.column_dimensions[column[0].column_letter].width = width

    print(f"导出完成：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
