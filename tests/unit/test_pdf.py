import uuid
      from services.ingestion.parsers.bank_statement import BankStatementParser
      from collections import Counter
      from libs.schemas.money import parse_inr_to_paise, format_inr
      
      pdf_path = "tests/sample_data/Statement_2026MTH02_329531405.pdf"
      with open(pdf_path, "rb") as f:
          raw_bytes = f.read()

      owner_id = uuid.uuid4()
      account_id = uuid.uuid4()
      txs = BankStatementParser().parse(raw_bytes, owner_id, account_id, password="gaur1112")

      print(f"Total: {len(txs)} transactions  ({sum(1 for t in txs if t.transaction_type=='CREDIT')} credits / {sum(1 for t in txs if t.transaction_type=='DEBIT')} debits)")

      cats = Counter(tx.category or "UNCATEGORISED" for tx in txs)
      print("\nCategory breakdown:")
      for cat, count in cats.most_common():
          print(f"  {cat:<20} {count}")

      total_credits = sum(parse_inr_to_paise(tx.raw_amount_text) for tx in txs if tx.transaction_type == "CREDIT")
      total_debits  = sum(parse_inr_to_paise(tx.raw_amount_text) for tx in txs if tx.transaction_type == "DEBIT")
      print(f"\nCredits: {format_inr(total_credits)}  Debits: {format_inr(total_debits)}")
      print("Expected: Credits ₹54,725.98  Debits ₹46,425.74")

      print("\n=== All 78 transactions ===")
      for i, tx in enumerate(txs, 1):
          print(f"{i:2}. {tx.transaction_date}  {tx.transaction_type:6}  {tx.raw_amount_text:>10}  {tx.category or 'UNKNOWN':<15}  {tx.raw_description[:70]}"