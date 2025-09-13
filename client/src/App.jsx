import { useState } from 'react';
import axios from 'axios';
import './App.css';

import Header from './components/Header';
import InputForm from './components/InputForm';
import ReportDisplay from './components/ReportDisplay';

function App() {

  const [formData, setFormData] = useState({
    destination: '',
    origin: '',
    dates: '',
    people: '',
    budget: '',
    interests: '',
    daily_spending_budget: '' 
  });


  const [reportData, setReportData] = useState({ markdown: '', map: null });
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const API_URL = 'http://127.0.0.1:8000/plan-trip';

  const handlePlanTrip = async () => {

    setErrors({});
    setReportData({ markdown: '', map: null });
    setIsLoading(true);

    const validateForm = () => {
      const newErrors = {};
      if (!formData.destination) newErrors.destination = "Destination is required.";
      if (!formData.origin) newErrors.origin = "Origin is required.";
      if (!formData.dates) newErrors.dates = "Dates are required.";
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

    const { destination, origin, dates, people, budget, interests, daily_spending_budget } = formData;

    const user_query = `Plan a trip to ${destination} from ${origin}. Dates: ${dates}. Number of people: ${people}. Our budget is around ${budget}. We are interested in ${interests}. Also, we plan to have a daily spending budget of about ${daily_spending_budget} per person.`;

   
    setIsLoading(true);
    setReportData('');

    try {
      const response = await axios.post(API_URL, { user_query });
      
      if (response.data && response.data.markdown_report) {
        setReportData({
          markdown: response.data.markdown_report,
          map: response.data.map_html
        });
      } else {
        setErrors({ form: response.data.error || 'An unknown error occurred.' });
      }
    } catch (err) {
      console.error(err);
      setErrors({ form: 'Failed to connect to the backend server.' });
    } finally {
      setIsLoading(false);
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
        />
      </div>
    </div>
  );
}

export default App;