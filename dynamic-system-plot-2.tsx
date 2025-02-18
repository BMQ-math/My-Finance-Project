import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const DynamicSystemPlot = () => {
  // Initial parameters with defaults
  const [params, setParams] = useState({
    a0: [0.5, 2.0],
    x0: 1.0,
    w0: [[0.95, 0.1], [0.05, 0.9]],
    W_evolve: [
      [0.99, 0.01, 0.00, 0.00],
      [0.00, 0.99, 0.00, 0.00],
      [0.00, 0.00, 0.99, 0.01],
      [0.00, 0.00, 0.00, 0.99]
    ],
    steps: 50
  });
  
  const [results, setResults] = useState({ x: [], a: [], w: [] });
  const [showCoefficients, setShowCoefficients] = useState(false);
  const [showTransitionMatrix, setShowTransitionMatrix] = useState(false);
  const [showWEvolutionMatrix, setShowWEvolutionMatrix] = useState(false);
  
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
  const handleW0Change = (row, col, value) => {
    const newW0 = [...params.w0.map(r => [...r])];
    handleNumericInput(value, (newValue) => {
      newW0[row][col] = newValue;
      setParams({...params, w0: newW0});
    });
  };
  
  // Handle W_evolve changes
  const handleWEvolveChange = (row, col, value) => {
    const newWEvolve = [...params.W_evolve.map(r => [...r])];
    handleNumericInput(value, (newValue) => {
      newWEvolve[row][col] = newValue;
      setParams({...params, W_evolve: newWEvolve});
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
  
  // Matrix multiplication function
  const matrixMultiply = (A, B) => {
    const rowsA = A.length;
    const colsA = A[0].length;
    const colsB = B[0].length;
    const result = Array(rowsA).fill().map(() => Array(colsB).fill(0));
    
    for (let i = 0; i < rowsA; i++) {
      for (let j = 0; j < colsB; j++) {
        for (let k = 0; k < colsA; k++) {
          result[i][j] += A[i][k] * B[k][j];
        }
      }
    }
    
    return result;
  };
  
  // Vector-matrix multiplication
  const vectorMatrixMultiply = (v, M) => {
    const result = Array(M[0].length).fill(0);
    
    for (let j = 0; j < M[0].length; j++) {
      for (let i = 0; i < v.length; i++) {
        result[j] += v[i] * M[i][j];
      }
    }
    
    return result;
  };
  
  // Flatten 2×2 matrix into vector [w00, w01, w10, w11]
  const flattenMatrix = (M) => {
    return [M[0][0], M[0][1], M[1][0], M[1][1]];
  };
  
  // Reshape vector [w00, w01, w10, w11] into 2×2 matrix
  const reshapeToMatrix = (v) => {
    return [
      [v[0], v[1]],
      [v[2], v[3]]
    ];
  };
  
  // Calculate system evolution
  const calculateSystem = () => {
    // Ensure all values are properly converted to numbers
    const a0 = params.a0.map(val => safeParseFloat(val));
    const x0 = safeParseFloat(params.x0);
    const w0 = params.w0.map(row => row.map(val => safeParseFloat(val)));
    const W_evolve = params.W_evolve.map(row => row.map(val => safeParseFloat(val)));
    const { steps } = params;
    
    const a = Array(steps + 1).fill().map(() => [0, 0]);
    const x = Array(steps + 1).fill(0);
    const w = Array(steps + 1).fill().map(() => [[0, 0], [0, 0]]);
    
    // Set initial values
    a[0] = [...a0];
    x[0] = x0;
    w[0] = w0.map(row => [...row]); // deep copy
    
    // Calculate evolution
    for (let i = 1; i <= steps; i++) {
      // Evolve W matrix
      const w_flat = flattenMatrix(w[i-1]);
      const w_next_flat = vectorMatrixMultiply(w_flat, W_evolve);
      w[i] = reshapeToMatrix(w_next_flat);
      
      // Calculate a[i]
      a[i] = vectorMatrixMultiply(a[i-1], w[i-1]);
      
      // Calculate x[i]
      x[i] = a[i-1][0] * x[i-1] + a[i-1][1];
    }
    
    // Format results for chart
    const chartData = x.map((value, index) => ({
      step: index,
      x: value,
      multiplier: a[index][0],
      constant: a[index][1],
      w00: w[index][0][0],
      w01: w[index][0][1],
      w10: w[index][1][0],
      w11: w[index][1][1]
    }));
    
    setResults({ x: chartData, a, w });
  };
  
  // Calculate on initial render
  useEffect(() => {
    calculateSystem();
  }, []);
  
  return (
    <div className="flex flex-col space-y-6 p-4 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold">Dynamic System Evolution with Evolving W</h2>
      
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
            <label className="block text-sm font-medium">Initial Transition Matrix (W₀)</label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <input
                type="text"
                value={params.w0[0][0]}
                onChange={(e) => handleW0Change(0, 0, e.target.value)}
                className="border p-1"
                placeholder="0.95"
              />
              <input
                type="text"
                value={params.w0[0][1]}
                onChange={(e) => handleW0Change(0, 1, e.target.value)}
                className="border p-1"
                placeholder="0.1"
              />
              <input
                type="text"
                value={params.w0[1][0]}
                onChange={(e) => handleW0Change(1, 0, e.target.value)}
                className="border p-1"
                placeholder="0.05"
              />
              <input
                type="text"
                value={params.w0[1][1]}
                onChange={(e) => handleW0Change(1, 1, e.target.value)}
                className="border p-1"
                placeholder="0.9"
              />
            </div>
          </div>
          
          <div>
            <div className="flex items-center">
              <label className="block text-sm font-medium">W Evolution Matrix (4×4)</label>
              <button 
                onClick={() => setShowWEvolutionMatrix(!showWEvolutionMatrix)}
                className="ml-2 text-sm text-blue-500 hover:text-blue-700"
              >
                {showWEvolutionMatrix ? 'Hide' : 'Show'}
              </button>
            </div>
            
            {showWEvolutionMatrix && (
              <div className="mt-2 p-2 border rounded bg-gray-50">
                <p className="text-xs mb-2">This matrix evolves the flattened W: [w00, w01, w10, w11]</p>
                {[0, 1, 2, 3].map(row => (
                  <div key={`we-row-${row}`} className="flex space-x-1 mb-1">
                    {[0, 1, 2, 3].map(col => (
                      <input
                        key={`we-${row}-${col}`}
                        type="text"
                        value={params.W_evolve[row][col]}
                        onChange={(e) => handleWEvolveChange(row, col, e.target.value)}
                        className="border p-1 w-12 text-xs"
                      />
                    ))}
                  </div>
                ))}
                <p className="text-xs mt-1">Default: Identity with small perturbations</p>
              </div>
            )}
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
          
          <div className="space-y-1">
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={showCoefficients}
                onChange={() => setShowCoefficients(!showCoefficients)}
              />
              <span>Show coefficient evolution</span>
            </label>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={showTransitionMatrix}
                onChange={() => setShowTransitionMatrix(!showTransitionMatrix)}
              />
              <span>Show W matrix evolution</span>
            </label>
          </div>
        </div>
        
        <div className="flex flex-col space-y-2">
          <p className="text-sm">
            This enhanced system now includes an evolving transition matrix W.
          </p>
          <p className="text-sm font-medium">Evolution equations:</p>
          <ul className="text-sm list-disc pl-5 space-y-1">
            <li>x[i] = a[i-1][0] * x[i-1] + a[i-1][1]</li>
            <li>a[i] = W[i-1] · a[i-1]</li>
            <li>W[i] = evolve(W[i-1]) using 4×4 matrix</li>
          </ul>
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
            <Line type="monotone" dataKey="x" stroke="#8884d8" name="x value" dot={false} strokeWidth={2} />
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
      
      {/* W matrix evolution chart */}
      {showTransitionMatrix && (
        <div className="h-64">
          <h3 className="text-lg font-semibold">W Matrix Evolution</h3>
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
              <Line type="monotone" dataKey="w00" stroke="#e84393" name="W[0][0]" dot={false} />
              <Line type="monotone" dataKey="w01" stroke="#00cec9" name="W[0][1]" dot={false} />
              <Line type="monotone" dataKey="w10" stroke="#fdcb6e" name="W[1][0]" dot={false} />
              <Line type="monotone" dataKey="w11" stroke="#6c5ce7" name="W[1][1]" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

export default DynamicSystemPlot;