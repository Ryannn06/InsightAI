import json, re
import pandas as pd
from openai import OpenAI

from app.utils.env import BASE_URL, API_KEY

# initialize OpenAI client
client = OpenAI(base_url=BASE_URL, 
                api_key=API_KEY)

# generate prompt and get response from OpenAI
def generate_prompt(system_text: str, user_text: str) -> str:
    response = client.chat.completions.create(
        model="openai/gpt-4o",
        temperature=0,
        max_tokens=4096,
        top_p=1,
        messages=[
            {
                "role":"system",
                "content": system_text
            },
            {
                "role":"user",
                "content": user_text
            }
        ]
    )

    return response

# system prompt
def system_prompt() -> str:
    return """
        You are a data analyst assistant. 
        Answer only in valid JSON; no explanations or extra text. 
        If unclear, return {}.
        """

# intent prompt
def intent_prompt(df: pd.DataFrame) -> str:
    column = df.columns.tolist()
    datatype = df.dtypes.to_list()

    column_info = list(zip(column, datatype, df.nunique()))
    column_text = "\n".join([f"- {col} ({dtype}, unique={n})" for col, dtype, n in column_info])

    row, col = df.shape

    prompt=f"""
        Given a dataset schema, generate up to 5 distinct analytical topics.

        Focus on:
        - comparisons
        - rankings
        - distributions
        - trends
        - relationships

        Rules:
        - Do NOT invent columns or generate charts.
        - Do NOT repeat topics or ask the same question in different ways.
        - Avoid analyses that would produce large or unreadable tables.
        - Prefer actionable, business-relevant insights.
        - Use ONLY these aggregations: mean, sum, count, min, max, median.
        - Use relationship ONLY as "correlation".
        - Use sort_by ONLY when explicit ordering is required (rankings or time trends).
        - For rankings, sort_by MUST match the aggregated measure.
        - For time trends, sort_by MUST be the time-related column.
        - Do NOT use the same column for group_by and measure
        - If a field is not needed, set it explicitly to null.

        No. of rows: {row}
        No. of columns: {col}
        Dataset columns:
        {column_text}

        Return ONLY valid JSON in this format:
        [
            {{
                "topic": "",
                "aggregation": null,
                "measure": null,
                "group_by": <null or one column>,
                "filters": null,
                "relationship": null,
                "sort_by": <null or one measure>,
                "ascending": null,
                "limit": null
            }}
        ]
        """
    
    return prompt

# insight prompt
def insight_prompt(response_json: list) -> str:
    # convert response to json string
    response_json_str = json.dumps(response_json)

    prompt=f"""
        Summarize the key insight for each topic in 2–3 sentences using ONLY the given results.

        Rules:
        - Do NOT create new analyses or invent data.
        - If multiple topics have the same results, keep only the best-fit topic.
        - If a topic contains multiple values, suggest "table".

        Chart rules:
        - "bar": rankings, comparisons, Top/Bottom.
        - "line": time trends only.
        - "pie": part-to-whole only.
        - "heatmap": correlation or matrix only.

        Return ONLY valid JSON:
        [
        {{
            "insight": "",
            "chart_type": "bar|line|pie|heatmap|table"
        }}
        ]

        Results:
        {response_json_str}

        """  
    return prompt

# combine intent and insight results
def combine_results(intents, insights) -> list:
    combined_results = []

    if isinstance(intents, str):
        intents = try_parse_json(intents)

    if isinstance(insights, str):
        insights = try_parse_json(insights)

    for intent, insight in zip(intents, insights):
        if isinstance(intent, str):
            intent = try_parse_json(intent)

        if isinstance(insight, str):
            insight = try_parse_json(insight)

        combined = intent.copy()
        combined.update(insight)
        combined_results.append(combined)
        
    return combined_results

# analyze intent from OpenAI response
def analyze_intent(df_original: pd.DataFrame, response : str) -> str:
    result_list = []
    data = try_parse_json(response)

    for item in data:
        try:
            # 1. fresh copy of the dataframe
            df = df_original.copy()
            
            topic = item.get("topic")
            agg = item.get("aggregation")
            group_by = item.get("group_by")
            measures = item.get("measure")
            relationship = item.get("relationship")
            filters = item.get("filters")
            sort_by = item.get("sort_by")
            ascending = item.get("ascending", True)
            limit = item.get("limit")

            # Normalize measures and group_by to lists
            if isinstance(measures, str):
                measures = [measures]
            #if group_by and isinstance(group_by, str):
                #group_by = [group_by]

            # 2. Apply filters
            if filters:
                # FIX: If filters is a single dict, turn it into a list so the loop works
                if isinstance(filters, dict):
                    # If it's the specific MongoDB style {'col': {'$ne': val}}, 
                    # you might need to flatten it, but for your loop to not CRASH:
                    filter_list = [filters]
                else:
                    filter_list = filters

                for f in filter_list:
                    # Double check f is a dict before calling .get()
                    if not isinstance(f, dict):
                        continue
                        
                    col, op, val = f.get("column"), f.get("operator"), f.get("value")
                    
                    if isinstance(col, list): col = col[0]
                    
                    if col and col in df.columns:
                        if op == "=":   df = df[df[col] == val]
                        elif op == ">":  df = df[df[col] > val]
                        elif op == "<":  df = df[df[col] < val]
                        elif op == ">=": df = df[df[col] >= val]
                        elif op == "<=": df = df[df[col] <= val]
                        elif op == "!=": df = df[df[col] != val]

            # 3. Relationship analysis
            if relationship == "correlation" and measures:
                rel_result = df[measures].corr()
                result_list.append({
                    "topic": topic,
                    "relationship": relationship,
                    "result": rel_result.to_dict()
                })

            # 4. Aggregation analysis
            elif agg:
                if group_by:
                    agg_result = df.groupby(group_by)[measures].agg(agg)
                    #agg_result = agg_result.reset_index()
                else:
                    agg_result = df[measures].agg(agg)

                # Ensure it is a DataFrame
                if isinstance(agg_result, pd.Series):
                    agg_result = agg_result.to_frame(name='value')
                    if agg_result.index.name is None:
                        agg_result.index.name = 'category'
                    # Reset this index too so 'category' becomes a column
                    #agg_result = agg_result.reset_index()

                # --- sorting ---
                if sort_by:
                    # If sort_by is a list ['total'], take the first string 'total'
                    if isinstance(sort_by, list) and len(sort_by) > 0:
                        sort_target = sort_by[0]
                    else:
                        sort_target = sort_by
                    
                    try:
                        # Try sorting by the requested column
                        agg_result = agg_result.sort_values(by=sort_target, ascending=ascending)
                    except:
                        # Fallback: Sort by the first numeric column available
                        if len(agg_result.columns) > 0:
                            agg_result = agg_result.sort_values(by=agg_result.columns[-1], ascending=ascending)

                if limit:
                    try:
                        agg_result = agg_result.head(int(limit))
                    except:
                        pass
                
                # Ensure index is string to avoid JSON serialization errors
                agg_result.index = agg_result.index.astype(str)
                final_data = agg_result.reset_index().to_dict(orient='records')
                
                result_list.append({
                    "topic": topic,
                    "aggregation": agg,
                    "result": final_data
                })

        except Exception as e:
            print(f"Error processing topic '{item.get('topic')}': {e}")
            continue

    if len(result_list) == 0:
        return None
        
    return json.dumps(result_list)

# analyze insight from OpenAI response
def analyze_insight(response: str) -> dict:
    data = try_parse_json(response)
    print(data)
    return data

# try parse json
def try_parse_json(response: str) -> dict:
    """
        Parse the OpenAI response string into a dictionary.
    """
    if not response:
        return []
    # Remove code fences if any
    response = re.sub(r"^```json|```$", "", response.strip(), flags=re.MULTILINE)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return []