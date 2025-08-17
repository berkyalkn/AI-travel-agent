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
    interests: ''
  });


  const [report, setReport] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const API_URL = 'http://127.0.0.1:8000/plan-trip';

  const handlePlanTrip = async () => {

    setErrors({});
    setReport(null);
    setIsLoading(true);

    const validateForm = () => {
      const newErrors = {};
      if (!formData.destination) newErrors.destination = "Destination is required.";
      if (!formData.origin) newErrors.origin = "Origin is required.";
      if (!formData.dates) newErrors.dates = "Dates are required.";
      if (!formData.people) newErrors.people = "Number of people is required.";
      if (!formData.budget) newErrors.budget = "Budget is required.";
      if (!formData.interests) newErrors.interests = "Please list at least one interest.";
      return newErrors;
    };

    const validationErrors = validateForm();
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      setIsLoading(false);
      return;
    }

    const { destination, origin, dates, people, budget, interests } = formData;
    const user_query = `Plan a trip to ${destination} from ${origin}. Dates: ${dates}. Number of people: ${people}. Our budget is around ${budget}. We are interested in ${interests}.`;

    setIsLoading(true);
    setReport('');

    try {
      const response = await axios.post(API_URL, { user_query });
      if (response.data && response.data.report) {
        setReport(response.data.report);
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
          report={report}
        />
      </div>
    </div>
  );
}

export default App;