from fastapi import UploadFile

import uuid
import pandas as pd
from collections import Counter
from io import StringIO, BytesIO
from app.utils.config import TEMP_DICT, RES_DICT, DURATION

import calendar

ALLOWED_EXTENSIONS = [".csv", ".xls", ".xlsx"]

# Get list of month names
full_months = list(calendar.month_name)[1:] # [January, February...]
short_months = list(calendar.month_abbr)[1:] # [Jan, Feb...]

# validate if csv or excel file
def validate_file(filename : str) -> bool:
    return any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)

# read and validate file
async def read_validate_file(file: UploadFile) -> str:
    contents = await file.read()

    if file.filename.endswith('.csv'):
        df = pd.read_csv(StringIO(contents.decode('utf-8')))
    else:
        df = pd.read_excel(BytesIO(contents))

    # if there is no enough columns
    if df.shape[1] < 2:
        return None
    
    # if there is missing header
    if df.columns.str.contains("Unnamed").any():
        return None
    
    # if there is no enough rows
    if df.dropna(how='all').shape[0] < 2:
        return None
    
    # dataset exceeds limit
    if df.shape[0] > 25000:
        return None

    # store data to server dict
    clean_id = str(uuid.uuid4())

    TEMP_DICT[clean_id] = df
    return clean_id


# load file
def load_file(clean_id : str) -> pd.DataFrame:
    return TEMP_DICT.get(clean_id)


# micro clean dataframe
def micro_clean(df : pd.DataFrame) -> pd.DataFrame:
    # format column naming convention
    df.columns = df.columns.astype(str).str.strip().str.replace(" ","_").str.lower()

    # remove duplicates and null
    df = df.drop_duplicates().dropna(how='all')

    for col in df.columns:
        df_check = df[df[col].notna()][col]
        
        if pd.api.types.is_object_dtype(df[col]):

            # Try numeric conversion first
            numeric_col = pd.to_numeric(df[col], errors='coerce')
            if numeric_col.notna().mean() > 0.8:
                df[col] = numeric_col.round(2)
                continue

            # Try datetime conversion
            datetime_col = pd.to_datetime(df[col], errors='coerce', infer_datetime_format=True)
            if datetime_col.notna().mean() > 0.8:
                df[col] = datetime_col
                df[col+'_month'] = datetime_col.dt.month
                df[col+'_month'] = datetime_col.dt.year
            
            # If month name is provided but in object
            if df[col].str.title().isin(full_months + short_months).all():
                month_col = to_month(df[col].str.strip().str.title())
                df[col] = month_col
                continue

            # Otherwise treat as string
            df[col] = df[col].apply(
                lambda x: str(x).strip().title() if pd.notnull(x) else x
            )

        # Already numeric columns (int/float) → round floats
        elif pd.api.types.is_float_dtype(df[col]):
            df[col] = df[col].round(2)

    return df

def to_month(df_col):
    if df_col.isin(full_months).any():
        return pd.Categorical(df_col, categories=full_months, ordered=True)

    if df_col.isin(short_months).any():
        return pd.Categorical(df_col, categories=short_months, ordered=True)

    else:
        return df_col

def clear_dict(clean_id : str):
    try:
        del TEMP_DICT[clean_id]
    except Exception as e:
        print(e)