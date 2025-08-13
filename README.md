
# Autonomous AI Travel Agent with Self-Correction

An AI travel agent built with React frontend, a FastAPI backend and a LangGraph for cyclical agent orchestration, powered by Groq and Tavily. This project demonstrates a stateful, multi-agent system that can plan, research, write, evaluate, and self-correct to generate a detailed travel itineraries based on a single natural language request, all served through an interactive web interface.

---

## Overview

This project automates the travel planning process through a full-stack application. A user interacts with a React-based web interface, submitting a high-level request (e.g., "a 5-day trip from Antalya to Rome for 2 people with a €2000 budget, focusing on history"). The request is sent to a FastAPI backend, which orchestrates a team of specialized AI agents. The system connects to live APIs for flight and hotel data and uses real-time web search for activities to produce a complete, logical, and budget-compliant travel plan, which is then rendered back to the user in the web UI.

The core of this project is its robust, decoupled architecture and its ability to not only generate a plan but also to evaluate its own work and autonomously self-correct.

---

## Features

- **Full-Stack Architecture:** Decoupled frontend (React) and backend (FastAPI) for a scalable and professional application structure.
- **Interactive Web Interface:** A clean, user-friendly UI built with React and Vite for submitting travel requests and viewing the final itinerary.
-   **Autonomous End-to-End Planning:** Generates a complete itinerary from a single natural language prompt.
- **Live API Integration:** Connects to real-time APIs for flights and hotels, and uses live web search (Tavily) for activities, grounding all plans in current, real-world data.
-   **Multi-Agent Orchestration:** Uses LangGraph to manage a stateful team of specialized agents (Planner, Researcher, Evaluator, etc.) that collaborate and share state to achieve a complex goal.
-   **Parallel Task Execution:**  Efficiently searches for flights and hotels concurrently to reduce planning time.
-   **Intelligent Self-Correction & Multi-Path Refinement:** A built-in Evaluator agent checks the plan against user constraints (e.g., budget). If the plan fails, it strategically decides whether to refine the flight or the hotel and triggers a targeted revision loop. The system intelligently selects the next-best option from the available choices in each loop.
-   **Robust & Formatted Outputs:** Delivers the final plan as both a structured Pydantic object and user-friendly, styled Markdown and HTML reports.

---

## System Architecture & Workflow

The system is modeled as a stateful graph (`StateGraph`) in LangGraph. Each node represents an agent or a specific function, and edges define the flow of information and control.


### Backend Workflow

1.  **Planner Agent:** Parses the user's natural language request into a structured `TripRequest` object containing all key constraints (destination, dates, budget, etc.).
2. **Parallel Data Gathering (Flight & Hotel Agents):** These agents run concurrently. They query live APIs for all possible flight and hotel options and use an LLM to make an initial selection based on a balance of cost and quality.
3. **Activity Extraction Agent:** Takes the user's interests, performs live web searches using Tavily, and uses a robust LLM pipeline to parse the raw search results into a structured list of Activity objects.
4. **Activity Scheduling Agent:** In a separate, focused step, this agent takes the structured list of activities and uses an LLM to organize them into a logical, day-by-day DailyPlan. This separation makes the process more reliable.
5. **Evaluator Agent:** The quality control gate. This agent analyzes the complete drafted plan (flight, hotel, costs) against user constraints and the available alternatives. It performs a strategic, value-based analysis to decide if the plan is optimal.
6. **Multi-Path Self-Correction Loop:** Based on the Evaluator's strategic decision, the graph uses a conditional edge to either approve the plan or trigger a self-correction loop. The loop can intelligently route the process back to the hotel_agent to find a cheaper hotel or back to the flight_agent to find a cheaper flight, depending on where the best potential saving lies.
7.  **Report Formatter:** Once the plan is approved, this final node creates the user-friendly .md and styled .html report files.
8. **FastAPI Endpoint:** The endpoint returns the final report as a JSON response to the React client.


```mermaid
graph TD
    subgraph "User's Browser"
        A[React Client UI]
    end

    subgraph "Backend Server"
        B(FastAPI Endpoint: /plan-trip)
        subgraph LangGraph Agentic Core
            C(Planner Agent)
            D{Flight Agent}
            E{Hotel Agent}
            F(Activity Extraction)
            G(Activity Scheduling)
            H(Evaluator Agent)
            I(Report Formatter)
        end
    end

    
    A -- "POST Request with user_query" --> B
    B -- "Invokes Agent" --> C
    C --> D & E
    D --> F
    E --> F
    F --> G
    G --> H
    H -- "Refine Hotel" --> E
    H -- "Refine Flight" --> D
    H -- "Plan OK / Max Retries" --> I
    I -- "Markdown Report" --> B
    B -- "JSON Response with Report" --> A
 ```

---

## Tech Stack

Category | Tool/Library | Purpose |
:---| :--- | :--- |
`AI Core` | **Groq** | Ultra-fast Llama 3 inference for all agentic reasoning. |
| | **LangChain** | Core framework for LLM interactions and tool definitions. |
| | **LangGraph** |  Orchestrates the stateful, multi-agent graph with cycles and parallel execution. |
| | **Pydantic** | Ensures data is structured and reliable throughout the entire workflow. |
`Backend` | **FastAPI** | A high-performance Python framework for building the API server. |
| | **Uvicorn** | The ASGI server that runs the FastAPI application.  |
| | **Python 3.10+** | The core programming language for the backend and agent logic. |
`Frontend` | **React** |Building the interactive user interface. |
| | **Vite** | A modern, fast frontend build tool and development server. |
| | **Axios** | Making HTTP requests from the client to the backend API. |
| | **React-Markdown** | Rendering the final Markdown report beautifully in the UI.|
| `Data Source` | **RapidAPI** | Platform for accessing live Flight and Hotel APIs.|
| | **Tavily** | Live web search for finding real-time activity information.


---

##  Installation & Setup

To get a local copy up and running, follow these steps.

**1. Clone the Repository**
```bash
git clone https://github.com/berkyalkn/AI-travel-agent
cd AI-travel-agent
```

**2. Set Up the Backend (server)**

```bash
# Navigate to the server directory
cd server

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

#Create a .env file in the root folder with your API keys:
#Open the .env file and enter your own API keys:
GROQ_API_KEY="your_groq_api_key"
TAVILY_API_KEY="your_tavily_api_key"
RAPIDAPI_KEY="your_rapid_api_key"

```

**3. Set Up the Frontend (client)**

```bash
# From the root directory, navigate to the client directory
cd ../client

# Install JavaScript dependencies
npm install
```

---

## How to Run

You need to run the backend and frontend servers simultaneously in two separate terminal windows.

1. Run the Backend Server:

- Open a terminal and navigate to the server/ directory.

- Activate the virtual environment (source venv/bin/activate).

- ```bash
  uvicorn main:app --reload
  ```

- The API server will be running at http://127.0.0.1:8000.


2. Run the Frontend Application:

- Open a second terminal and navigate to the client/ directory.

- Run the following command:

- ```bash
  npm run dev
  ```

- This will automatically open the web application in your browser, usually at http://localhost:5173.


Now you can use the web interface to plan your trip!

> **Note on CORS:** The React frontend and FastAPI backend run on different ports (`localhost:5173` and `localhost:8000` respectively). The backend is configured with FastAPI's `CORSMiddleware` to explicitly allow requests from the frontend's origin during development. If you change the frontend port, you will need to update the `origins` list in `server/main.py`.

--- 

## Example Usage

A user simply types their request into the web interface. The more detail provided, the better the resulting plan will be.

> **User's Request:**
> "I want to plan trip to New York from Antalya for me and my two best friends between 25.09.205 and 28.09.2025 . We are interested in adventure, museums, and food, and our total budget is around 8,000 euros."

#### What You Get

After processing, the application renders a complete and detailed travel plan directly in the user interface, which includes:

-   **A Budget Summary:** A clear breakdown of the total estimated cost versus the user's budget.
-   **Flight & Hotel Details:** The selected flight and hotel, including pricing and ratings.
-   **A Day-by-Day Itinerary:** A logical schedule of activities and experiences tailored to the user's interests.


---

##  Key AI Concepts Demonstrated

This project is a practical implementation of several advanced concepts in AI engineering:
-   **Structured Output:** Forcing all LLM outputs, from initial planning (TripRequest) to the final plan (Itinerary) and evaluation (EvaluationResult), into reliable Pydantic schemas to ensure data integrity and predictable workflows.
-   **Tool Binding & Live API Integration:** Enabling agents to use external functions to gather information from live, real-time APIs (for flights and hotels) and the unstructured web (for activities via Tavily Search).
-   **Parallelization:** Executing independent data-gathering tasks (flight and hotel searches) concurrently to significantly reduce total execution time.
-   **Advanced Routing & Conditional Logic:** Using conditional edges to create a multi-path, self-correcting loop. The graph dynamically routes its own execution path back to different agents (hotel_agent or flight_agent) based on the strategic output of the Evaluator agent.
-   **Stateful Multi-Agent Orchestration:** Using LangGraph to manage a complex, multi-step process where multiple specialized agents collaborate and share information through a persistent state (TripState).
-   **Evaluation & Reflection:** Creating a dedicated Evaluator agent that critiques the system's own output against user constraints and available alternatives, enabling true autonomous decision-making and refinement.