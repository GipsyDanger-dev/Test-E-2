import csv, json
from dataclasses import dataclass
from pathlib import Path
from .schemas import CRMSourceRecord, EmailInput, StaffMember

ROOT = Path(__file__).resolve().parents[1] / 'data'
@dataclass
class DataPack:
    staff: list[StaffMember]; crm_records: list[CRMSourceRecord]; emails: list[EmailInput]; documents: dict[str,str]; warnings: list[dict]; raw_rows: dict[str,str]
def load_data_pack() -> DataPack:
    staff=[StaffMember.model_validate(x) for x in json.loads((ROOT/'staff_directory.json').read_text())]
    emails=[EmailInput.model_validate(x) for x in json.loads((ROOT/'emails.json').read_text())]
    docs={p.name:p.read_text() for p in (ROOT/'documents').glob('*.txt')}
    lines=(ROOT/'crm.csv').read_text().splitlines(); header=next(csv.reader([lines[0]])); records=[]; warnings=[]; raw={}
    for line in lines[1:]:
        values=next(csv.reader([line])); rid=values[0] if values else 'unknown'; raw[rid]=line
        if len(values)==len(header)-1:
            # The prescribed malformed C002 row omitted only phone, so realign its trailing values conservatively.
            data=dict(zip(header[:4],values[:4])); data.update(dict(zip(header[5:],values[4:]))); data['phone']=None
            msg='CRM row is missing the phone field; trailing fields were realigned conservatively.'; warnings.append({'record_id':rid,'type':'column_count_mismatch','severity':'warning','message':msg,'raw_row':line})
        else:
            data=dict(zip(header,values))
            if len(values)!=len(header): warnings.append({'record_id':rid,'type':'column_count_mismatch','severity':'warning','message':'CRM row contains fewer fields than the header.','raw_row':line})
        records.append(CRMSourceRecord.model_validate({k:v for k,v in data.items() if not k.startswith('_')}))
    return DataPack(staff,records,emails,docs,warnings,raw)
