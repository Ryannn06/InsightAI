# InsightAI

**InsightAI** is a simple web app that helps users turn uploaded datasets into meaningful,AI-driven insights. Built lightweight and modular using FastAPI (backend) and modern web tools (frontend).

## <br>Features
InsightAI empowers users to effortlessly transform raw data into actionable insights:
- Upload datasets in seconds to kickstart analysis
- Automate cleaning and processing for accurate, reliable results every time
- Generate meaningful analytical summaries with intelligent, AI-driven insight
- Explore results in dynamic, responsive graphs for clear and intuitive visualization


## <br>How AI Works

InsightAI uses OpenAI to automatically suggest analysis steps and generate insights based on the uploaded dataset.
Users don’t need to write any prompts or instructions.


### 1. Schema Preparation
After a dataset is uploaded, InsightAI looks at the column names and data types (numeric, categorical, or date/time) to create a simple schema.
This schema is prompted to the AI model as context, so the AI knows what each column represents.


### 2. Prompt-Based Intent Generation
The AI is prompted with the schema to suggest analysis steps, such as:
- Summing or averaging numeric columns
- Grouping data by categories
- Counting values or creating basic distributions

These outputs are structured analysis instructions and do not include any executable code.


### 3. Intent Validation
All AI-generated analysis instructions are checked against:
- Supported operations (sum, average, group, etc.)
- Dataset structure and consistency
- Application rules

Any instructions that don’t meet these rules or inexecutable are disregarded.


### 4. Code Execution
The validated analysis instructions are executed using predefined Python functions.
For the same dataset and instructions, the results are always consistent and reproducible.


### 5. Prompt-Based Insight Generation
The results of the executed analyses are prompted back to the AI, which generates plain-language insights to help users interpret the findings.


### 6. Data Visualization
The results are prepared as structured datasets and displayed in tables or visualizations for easy review.


## <br>Architectural Principles

- AI generates analytic ideas and insights only from column names, datatypes, and aggregated results.
- The system does not run any AI-generated code.
- Computations are structured and deterministic.


## <br>Technology Stack

### Backend
- **FastAPI** – High-performance Python web framework
- **Python** – Core application and data processing logic

### Frontend
- **HTML / Jinja2** – Server-side rendering
- **Bootstrap** – Responsive layout and tables
- **JavaScript** – Client-side interactions


---
*Developed by: Ryannn06*