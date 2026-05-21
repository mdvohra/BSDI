// src/components/ReportButton.js
import React from 'react';
import jsPDF from 'jspdf';

const ReportButton = ({ predictionData }) => {
  const generatePDFReport = () => {
    if (!predictionData) {
      alert("No data available to generate the report.");
      return;
    }

    const { 
      tree_count = "N/A", 
      total_area = "N/A", 
      averageTreeArea = "N/A", 
      image 
    } = predictionData;

    const doc = new jsPDF();
    doc.setFontSize(16);
    doc.text("Tree Health Analysis Report", 10, 20);

    // Add analysis summary
    doc.setFontSize(12);
    doc.text(`Tree Count: ${tree_count}`, 10, 40);
    doc.text(`Total Area: ${total_area !== "N/A" ? total_area + " sq.m" : "N/A"}`, 10, 50);
    doc.text(
      `Average Tree Area: ${
        averageTreeArea !== "N/A" ? averageTreeArea + " sq.m" : "N/A"
      }`,
      10,
      60
    );

    // Optional: Add image (if available)
    if (image) {
      doc.addImage(image, "PNG", 10, 70, 180, 100);
    }

    // Save the PDF
    doc.save("Tree_Health_Report.pdf");
  };

  return (
    <button
      onClick={generatePDFReport}
      className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600"
    >
      Generate PDF Report
    </button>
  );
};

export default ReportButton;
