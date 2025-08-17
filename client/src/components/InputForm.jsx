import React from 'react';

function InputForm({ query, setQuery, handlePlanTrip, isLoading }) {
  return (
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
  );
}

export default InputForm;