import { useState } from 'react';
import axios from 'axios';
import './App.css';

import Header from './components/Header';
import InputForm from './components/InputForm';
import ReportDisplay from './components/ReportDisplay';

function App() {
  const [query, setQuery] = useState('');
  const [report, setReport] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const API_URL = 'http://127.0.0.1:8000/plan-trip';

  const handlePlanTrip = async () => {
    if (!query) {
      setError('Please describe the trip you want to plan.');
      return;
    }
    
    setIsLoading(true);
    setError('');
    setReport('');

    try {
      const response = await axios.post(API_URL, { user_query: query });
      if (response.data.report) {
        setReport(response.data.report);
      } else if (response.data.error) {
        setError(response.data.error);
      } else {
        setError('An unknown error occurred. The report could not be generated.');
      }
    } catch (err) {
      console.error(err);
      setError('Failed to connect to the backend server. Please ensure the server is running.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <div className="main-container">
        <Header />
        <InputForm 
          query={query}
          setQuery={setQuery}
          handlePlanTrip={handlePlanTrip}
          isLoading={isLoading}
        />
        <ReportDisplay 
          isLoading={isLoading}
          error={error}
          report={report}
        />
      </div>
    </div>
  );
}

export default App;