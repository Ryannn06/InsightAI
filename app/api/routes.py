from fastapi import APIRouter, UploadFile, File, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import pandas as pd
from io import StringIO, BytesIO
import time

from app.crud import file_handler
from app.utils.config import TEMP_DICT, RES_DICT, DURATION
from app.crud.openai import intent_prompt, insight_prompt, system_prompt, generate_prompt, analyze_intent, analyze_insight, combine_results

from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent
json_path = BASE_DIR / "lib" / "TEST_RES.json"
json_path_int = BASE_DIR / "lib" / "TEST_INTRES.json"
json_path_ins = BASE_DIR / "lib" / "TEST_INSRES.json"

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

ERROR_MESSAGES = {
    "analysis_failed": "Something went wrong while executing the analysis. Please try again.",
    "invalid_dataset": "Invalid file structure or size exceeds system limits.",
    "invalid_format": "CSV or Excel files are the only formats allowed.",
    "session_expired": "Your session has expired. Please upload your file again.",
    "not_found": "Page not found (404).",
    "forbidden":"You don’t have permission to access this (403).",
    "failed_read":"Failed to read the file."
}

@router.get('/', response_class=HTMLResponse)
def index(request : Request):   
    # check if there is active session
    session_id = request.cookies.get("session_id")
    if session_id and session_id in TEMP_DICT:
        return RedirectResponse(url=f'/report/{session_id}', status_code=303)
    
    # otherwise
    error_slug = request.cookies.get("error_msg")
    display_text = ERROR_MESSAGES.get(error_slug)

    response =  templates.TemplateResponse( "index.html",
                                           {"request": request,
                                            "error":display_text})
    
    # clear cookie so it does not show on refresh
    if error_slug:
        response.delete_cookie("error_msg")
    return response

@router.post('/upload', response_class=HTMLResponse)
async def upload_file(request : Request, file: UploadFile = File(...)):
    # validate file type
    if not file_handler.validate_file(file.filename.lower()):
        response = RedirectResponse(url='/', status_code=303)
        response.set_cookie(key="error_msg", value="invalid_format", max_age=5)

        return response
    
    # read file to dataframe
    try:
        clean_id = await file_handler.read_validate_file(file)
        if clean_id is None:
            response = RedirectResponse(url='/', status_code=303)
            response.set_cookie(key="error_msg", value="invalid_dataset", max_age=5)

            return response
        
    except Exception as e:
        response = RedirectResponse(url='/', status_code=303)
        response.set_cookie(key="error_msg", value="failed_read")

        return response
    
    # Create the redirect object first
    redirect = RedirectResponse(url=f'/clean/{clean_id}', status_code=303)

    # Set the cookie on the object
    redirect.set_cookie(key="session_id", value=clean_id, httponly=True)

    return redirect
    

@router.get('/clean/{clean_id}')
def clean(request : Request, clean_id : str):
    # set timer
    start = time.perf_counter()
    
    # if cookie_id and clean_id do not match
    cookie_id = request.cookies.get("session_id")
    if cookie_id and cookie_id != clean_id:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="error_msg", value="forbidden", max_age=5)

        return response

    # else proceed
    df = file_handler.load_file(clean_id)
    if df is None:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="error_msg", value="not_found", max_age=5)

        return response
    
    try:
        sum([i**2 for i in range(1000000)])

        # micro clean dataframe
        processed_df = file_handler.micro_clean(df)

        # generate intent
        intent = generate_prompt(system_prompt(), intent_prompt(processed_df))
        intent_res = analyze_intent(processed_df, intent.choices[0].message.content)

        if intent_res is None:
            TEMP_DICT.pop(clean_id, None)
            RES_DICT.pop(clean_id, None)
            DURATION.pop(clean_id, None)

            response = RedirectResponse(url='/', status_code=303)
            response.delete_cookie("session_id")
            
            response.set_cookie(key="error_msg", value="analysis_failed", max_age=5)
            
            return response
        
        # generate insight
        insight = generate_prompt(system_prompt(), insight_prompt(intent_res))
        insight_res = analyze_insight(insight.choices[0].message.content)

        # combine intent and insight results
        combined_results = combine_results(intent_res, insight_res)

        end = time.perf_counter()
        duration = end - start

        # save to temporary dict
        TEMP_DICT[clean_id] = processed_df #update to processed df
        RES_DICT[clean_id] = combined_results
        DURATION[clean_id] = duration

    except Exception as e:
        print(f"Error during cleaning: {e}")

        TEMP_DICT.pop(clean_id, None)
        RES_DICT.pop(clean_id, None)
        DURATION.pop(clean_id, None)

        response = RedirectResponse(url='/', status_code=303)
        response.delete_cookie("session_id")
        response.set_cookie(key="error_msg", value="analysis_failed", max_age=5)
        
        return response

    return RedirectResponse(url=f'/report/{clean_id}', status_code=303)


@router.get('/report/{clean_id}')
def report(request : Request, clean_id : str):
    cookie_id = request.cookies.get("session_id")
    
    # cookie does not exist
    if not cookie_id:
        response = RedirectResponse(url='/', status_code=303)
        response.set_cookie(key="error_msg", value="not_found", max_age=5)
        
        return response
    
    # cookie and clean_id not match
    if cookie_id and cookie_id != clean_id:
        response = RedirectResponse(url='/', status_code=303)
        response.set_cookie(key="error_msg", value="forbidden", max_age=5)
        
        return response
    
    # else
    processed_df = TEMP_DICT.get(clean_id)
    combined_results = RES_DICT.get(clean_id)
    duration = DURATION.get(clean_id)

    if processed_df is None or combined_results is None or duration is None:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="error_msg", value="not_found", max_age=5)

        return response
    
    return templates.TemplateResponse(
        "report.html",
        {
            "request":request,
            "columns": list(processed_df.columns),
            "dtypes":processed_df.dtypes,
            "rows": processed_df.to_dict("records"),
            "openai_response": combined_results,
            "success":"Data is successfully analyzed.",
            "runtime":round(duration,2),
            "is_active":True
        }
    )


@router.get('/quit_report', response_class=HTMLResponse)
async def quit_report(request : Request):
    cookie_id = request.cookies.get("session_id")
        
    TEMP_DICT.pop(cookie_id, None)
    RES_DICT.pop(cookie_id, None)
    DURATION.pop(cookie_id, None)

    response = RedirectResponse(url='/', status_code=303)
    response.delete_cookie("session_id")

    return response

@router.get('/about', response_class=HTMLResponse)
def about(request : Request):
    # check if there is active session
    session_id = request.cookies.get("session_id")
    if session_id and session_id in TEMP_DICT:
        return RedirectResponse(url=f'/report/{session_id}', status_code=303)
    
    return templates.TemplateResponse("about.html", 
                                      {"request":request})