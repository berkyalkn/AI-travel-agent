import { useState } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import './App.css'; // Stil dosyamızı import ediyoruz

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
      
      const response = await axios.post(API_URL, {
        user_query: query
      });

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
      <header className="App-header">
        <div className="title-container">
          <h1>AI Travel Agent</h1>
          <span className="plane-icon">✈️</span>
        </div>
        <p>Describe your trip, and I'll create a detailed itinerary for you.</p>
        <div className="input-area">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g., Plan a 5-day trip to Tokyo for 2 people in March. We love food, technology, and temples. Our budget is around 3000 euros."
            rows={6}
            disabled={isLoading}
          />
          <button onClick={handlePlanTrip} disabled={isLoading}>
            {isLoading ? 'Planning Your Trip...' : 'Plan My Trip'}
          </button>
        </div>
      </header>
      
      <main className="report-container">
        {error && <div className="error-box">{error}</div>}
        {isLoading && <div className="loading-spinner"></div>}
        {report && (
          <div className="markdown-content">
            <ReactMarkdown>{report}</ReactMarkdown>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
