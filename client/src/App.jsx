import { useState, useRef } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import './App.css';

import Header from './components/Header';
import InputForm from './components/InputForm';
import ReportDisplay from './components/ReportDisplay';

const formatDate = (date) => {
  if (!date) return '';
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${year}-${month}-${day}`;
};

function App() {

  const [formData, setFormData] = useState({
    destination: '',
    origin: '',
    startDate: null,
    endDate: null,
    people: '',
    budget: '',
    interests: '',
    daily_spending_budget: '' 
  });

  const [agentStatus, setAgentStatus] = useState('');
  const [reportData, setReportData] = useState({ markdown: '', map: null });
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const abortControllerRef = useRef(null);

  const API_URL = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/plan-trip-stream`;

  const handlePlanTrip = async () => {

    setErrors({});
    setReportData({ markdown: '', map: null });
    setAgentStatus('Connecting to the AI Travel Agent...'); 
    setIsLoading(true);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    const { destination, origin, startDate, endDate, people, budget, interests, daily_spending_budget } = formData;
    
    if (!destination || !origin || !startDate || !endDate || !people || !budget) {
       setErrors({ form: "Please fill in all required fields." });
       setIsLoading(false);
       return;
    }

    const formattedDates = `${formatDate(startDate)} to ${formatDate(endDate)}`;
    const user_query = `Plan a trip to ${destination} from ${origin}. Dates: ${formattedDates}. Number of people: ${people}. Our budget is around ${budget}. We are interested in ${interests}. Also, we plan to have a daily spending budget of about ${daily_spending_budget} per person.`;

    try {
      await fetchEventSource(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_query }),
        signal: signal,
        
        openWhenHidden: true,

        async onopen(response) {
          if (response.ok && response.headers.get('content-type')?.startsWith('text/event-stream')) {
            console.log("Stream connection successfully established.");
            return; 
          } else {
            console.error(`Stream connection failed. Status: ${response.status}`);
            throw new Error(`Server connection error. Status: ${response.status}`);
          }
        },

        onmessage(event) {
          try {
             if (event.event === 'status') {
               const data = JSON.parse(event.data);
               setAgentStatus(data.message);
             } else if (event.event === 'final_report') {
               const data = JSON.parse(event.data);
               setReportData({
                 markdown: data.markdown_report,
                 map: data.map_html
               });
               setAgentStatus('Your itinerary is ready!');
               setIsLoading(false);
               abortControllerRef.current?.abort();
             } else if (event.event === 'error') {
                 const data = JSON.parse(event.data);
                 setErrors({ form: data.message || 'An error occurred.' });
                 setIsLoading(false);
                 abortControllerRef.current?.abort();
             }
          } catch (e) {
             console.log("Message parse error", e);
          }
        },

        onclose() {
          console.log("Connection closed by the server.");
        },

        onerror(err) {
          console.error("Stream connection error:", err);
          
          if (signal.aborted) {
             console.log("User aborted.");
             return;
          }

          setErrors({ form: "Connection lost. The AI took too long to respond." });
          setIsLoading(false);

        }
      });
    } catch (err) {
      console.error("Fetch error:", err);
      if (!signal.aborted) {
         setErrors({ form: "Failed to connect to server." });
         setIsLoading(false);
      }
    }
  };

  return (
    <div className="App">
      <div className="main-container">
        <Header />
        <InputForm 
          formData={formData}
          setFormData={setFormData}
          handlePlanTrip={handlePlanTrip}
          isLoading={isLoading}
          errors={errors}
        />
        <ReportDisplay 
          isLoading={isLoading}
          error={errors.form}
          reportData={reportData}
          agentStatus={agentStatus} 
        />
      </div>
    </div>
  );
}

export default App;