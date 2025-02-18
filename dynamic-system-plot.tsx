import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const DynamicSystemPlot = () => {
  // Initial parameters with some defaults
  const [params, setParams] = useState({
    a0: [0.5, 2.0],
    x0: 1.0,
    w: [[0.95, 0.1], [0.05, 0.9]],
    steps: 50
  });
  
  const [results, setResults] = useState({ x: [], a: [] });
  const [showCoefficients, setShowCoefficients] = useState(false);
  
  // Custom input handler that properly handles numbers, negative signs, and decimals
  const handleNumericInput = (value, callback) => {
    // Allow empty, minus sign, decimal point, or valid numbers
    if (
      value === '' || 
      value === '-' || 
      value === '.' || 
      value === '-.' ||
      !isNaN(parseFloat(value))
    ) {
      callback(value);
    }
  };
  
  // Functions to handle matrix changes
  const handleMatrixChange = (row, col, value) => {
    const newW = [...params.w.map(r => [...r])];
    handleNumericInput(value, (newValue) => {
      newW[row][col] = newValue;
      setParams({...params, w: newW});
    });
  };
  
  // Handle a0 changes
  const handleA0Change = (index, value) => {
    const newA0 = [...params.a0];
    handleNumericInput(value, (newValue) => {
      newA0[index] = newValue;
      setParams({...params, a0: newA0});
    });
  };
  
  // Handle x0 changes
  const handleX0Change = (value) => {
    handleNumericInput(value, (newValue) => {
      setParams({...params, x0: newValue});
    });
  };
  
  // Convert string value to number safely
  const safeParseFloat = (value) => {
    if (value === '' || value === '-' || value === '.' || value === '-.') return 0;
    const parsed = parseFloat(value);
    return isNaN(parsed) ? 0 : parsed;
  };
  
  // Calculate system evolution
  const calculateSystem = () => {
    // Ensure all values are properly converted to numbers
    const a0 = params.a0.map(val => safeParseFloat(val));
    const x0 = safeParseFloat(params.x0);
    const w = params.w.map(row => row.map(val => safeParseFloat(val)));
    const { steps } = params;
    
    const a = Array(steps + 1).fill().map(() => [0, 0]);
    const x = Array(steps + 1).fill(0);
    
    // Set initial values
    a[0] = [...a0];
    x[0] = x0;
    
    // Calculate evolution
    for (let i = 1; i <= steps; i++) {
      // Matrix multiplication for a[i]
      const a_prev = a[i-1];
      a[i][0] = w[0][0] * a_prev[0] + w[0][1] * a_prev[1];
      a[i][1] = w[1][0] * a_prev[0] + w[1][1] * a_prev[1];
      
      // Calculate x[i]
      x[i] = a[i-1][0] * x[i-1] + a[i-1][1];
    }
    
    // Format results for chart
    const chartData = x.map((value, index) => ({
      step: index,
      x: value,
      multiplier: a[index][0],
      constant: a[index][1]
    }));
    
    setResults({ x: chartData, a });
  };
  
  // Calculate on initial render
  useEffect(() => {
    calculateSystem();
  }, []);
  
  return (
    <div className="flex flex-col space-y-6 p-4 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold">Dynamic System Evolution</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-4 p-4 border rounded">
          <h3 className="text-lg font-semibold">Parameters</h3>
          
          <div>
            <label className="block text-sm font-medium">Initial Coefficient Vector (a₀)</label>
            <div className="flex space-x-2 mt-1">
              <input
                type="text"
                value={params.a0[0]}
                onChange={(e) => handleA0Change(0, e.target.value)}
                className="border p-1 w-20"
                placeholder="-0.5"
              />
              <input
                type="text"
                value={params.a0[1]}
                onChange={(e) => handleA0Change(1, e.target.value)}
                className="border p-1 w-20"
                placeholder="2.0"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium">Initial Value (x₀)</label>
            <input
              type="text"
              value={params.x0}
              onChange={(e) => handleX0Change(e.target.value)}
              className="border p-1 w-20 mt-1"
              placeholder="1.0"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium">Transition Matrix (W)</label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <input
                type="text"
                value={params.w[0][0]}
                onChange={(e) => handleMatrixChange(0, 0, e.target.value)}
                className="border p-1"
                placeholder="0.95"
              />
              <input
                type="text"
                value={params.w[0][1]}
                onChange={(e) => handleMatrixChange(0, 1, e.target.value)}
                className="border p-1"
                placeholder="0.1"
              />
              <input
                type="text"
                value={params.w[1][0]}
                onChange={(e) => handleMatrixChange(1, 0, e.target.value)}
                className="border p-1"
                placeholder="0.05"
              />
              <input
                type="text"
                value={params.w[1][1]}
                onChange={(e) => handleMatrixChange(1, 1, e.target.value)}
                className="border p-1"
                placeholder="0.9"
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">Tip: You can enter negative values like -0.5</p>
          </div>
          
          <div>
            <label className="block text-sm font-medium">Number of Steps</label>
            <input
              type="number"
              min="5"
              max="100"
              value={params.steps}
              onChange={(e) => setParams({...params, steps: parseInt(e.target.value)})}
              className="border p-1 w-20 mt-1"
            />
          </div>
          
          <button
            onClick={calculateSystem}
            className="bg-blue-500 hover:bg-blue-600 text-white py-2 px-4 rounded"
          >
            Calculate
          </button>
          
          <div>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={showCoefficients}
                onChange={() => setShowCoefficients(!showCoefficients)}
              />
              <span>Show coefficient evolution</span>
            </label>
          </div>
        </div>
        
        <div className="flex flex-col space-y-2">
          <p className="text-sm">
            This visualization shows how x evolves over time with the given parameters.
            The sequence follows: x[i] = a[i-1][0] * x[i-1] + a[i-1][1]
          </p>
          <p className="text-sm">
            The coefficients themselves evolve according to: a[i] = W · a[i-1]
          </p>
          <div className="mt-4">
            <p className="font-medium">Final value: x[{params.steps}] = {results.x[params.steps]?.x.toFixed(4) || 'calculating...'}</p>
          </div>
        </div>
      </div>
      
      {/* Main chart */}
      <div className="h-64 md:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={results.x}
            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="step" label={{ value: 'Step', position: 'insideBottomRight', offset: -5 }} />
            <YAxis label={{ value: 'Value', angle: -90, position: 'insideLeft' }} />
            <Tooltip formatter={(value) => value.toFixed(4)} />
            <Legend />
            <Line type="monotone" dataKey="x" stroke="#8884d8" name="x value" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      
      {/* Coefficient evolution chart */}
      {showCoefficients && (
        <div className="h-64">
          <h3 className="text-lg font-semibold">Coefficient Evolution</h3>
          <ResponsiveContainer width="100%" height="90%">
            <LineChart
              data={results.x}
              margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="step" />
              <YAxis />
              <Tooltip formatter={(value) => value.toFixed(4)} />
              <Legend />
              <Line type="monotone" dataKey="multiplier" stroke="#ff7300" name="a[i][0] (multiplier)" dot={false} />
              <Line type="monotone" dataKey="constant" stroke="#00b894" name="a[i][1] (constant)" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

export default DynamicSystemPlot;