import { useState } from 'react';
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

  const API_URL = `${import.meta.env.VITE_API_URL}/plan-trip-stream`;

  const handlePlanTrip = async () => {

    setErrors({});
    setReportData({ markdown: '', map: null });
    setAgentStatus('Connecting to the AI Travel Agent...'); 
    setIsLoading(true);

    const validateForm = () => {
      const newErrors = {};
      if (!formData.destination) newErrors.destination = "Destination is required.";
      if (!formData.origin) newErrors.origin = "Origin is required.";
      if (!formData.startDate || !formData.endDate) newErrors.dates = "Start and end dates are required.";
      if (!formData.people) newErrors.people = "Number of people is required.";
      if (!formData.budget) newErrors.budget = "Budget is required.";
      if (!formData.interests) newErrors.interests = "Please list at least one interest.";
      if (!formData.daily_spending_budget) newErrors.daily_spending_budget = "Daily Spending Budget is required.";
      return newErrors;
    };

    const validationErrors = validateForm();
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      setIsLoading(false);
      return;
    }

    const { destination, origin, startDate, endDate, people, budget, interests, daily_spending_budget } = formData;

    const formattedDates = `${formatDate(startDate)} to ${formatDate(endDate)}`;

    const user_query = `Plan a trip to ${destination} from ${origin}. Dates: ${formattedDates}. Number of people: ${people}. Our budget is around ${budget}. We are interested in ${interests}. Also, we plan to have a daily spending budget of about ${daily_spending_budget} per person.`;

   
    setIsLoading(true);
    setReportData({ markdown: '', map: null });

    await fetchEventSource(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ user_query }),

      async onopen(response) {
        const contentType = response.headers.get('content-type');
        console.log("Content-Type header from server:", contentType);
    
        if (response.ok && contentType && contentType.startsWith('text/event-stream')) {
          console.log("Stream connection successfully established.");
        } else {
          console.error(`Stream could not be opened. Expected 'text/event-stream', but received '${contentType}'`, response);
          setErrors({ form: `Server connection error. Invalid content type: ${contentType || 'None received'}` });
          setIsLoading(false);
        }
      },

      onmessage(event) {
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
        } else if (event.event === 'error') {
            const data = JSON.parse(event.data);
            setErrors({ form: data.message || 'An error occurred during planning.' });
            setIsLoading(false);
        }
      },

      onclose() {
        console.log("Connection closed by the server.");
        if (isLoading) {
            setIsLoading(false);
            setAgentStatus("Stream ended before the report was complete.");
        }
      },

      onerror(err) {
        console.error("Stream connection error:", err);
        setErrors({ form: "Failed to connect to the streaming server. Check the console for details." });
        setIsLoading(false);
      }
    });
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