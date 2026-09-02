import { createContext, useContext, useState } from 'react';

const ModelContext = createContext();

export function ModelProvider({ children }) {
  const [selectedModel, setSelectedModel] = useState(() => {
    return localStorage.getItem('raven_selected_model') || 'gemini-3.6-flash';
  });

  const changeModel = (modelId) => {
    setSelectedModel(modelId);
    localStorage.setItem('raven_selected_model', modelId);
  };

  return (
    <ModelContext.Provider value={{ selectedModel, setSelectedModel: changeModel }}>
      {children}
    </ModelContext.Provider>
  );
}

export function useModel() {
  const ctx = useContext(ModelContext);
  if (!ctx) {
    throw new Error('useModel must be used within a ModelProvider');
  }
  return ctx;
}
