import React, { useState, useEffect } from 'react';
import ImageUploader from './components/ImageUploader';
import ImageViewer from './components/ImageViewer';
import Chat from './components/Chat';
import ExportButton from './components/ExportButton';
import { downloadGeoJSON, downloadShapefile } from './services/api';
import { Row, Col, Container } from 'react-bootstrap';
// import MapViewer from './components/MapViewer';

const SatelliteImage = () => {
  const [predictionData, setPredictionData] = useState(null);
  const [uploadedImage, setUploadedImage] = useState(null);
  const [predictionImageUrl, setPredictionImageUrl] = useState(null);
  const [fileType, setFileType] = useState(null);
  useEffect(() => {
    // Cleanup function to revoke object URLs when component unmounts
    return () => {
      if (uploadedImage) {
        URL.revokeObjectURL(uploadedImage);
      }
      if (predictionImageUrl) {
        URL.revokeObjectURL(predictionImageUrl);
      }
    };
  }, [uploadedImage, predictionImageUrl]);

  const handleUploadSuccess = (data) => {
    // Convert the hex string back to a Blob URL for image display
    const byteArray = new Uint8Array(
      data.image.match(/.{1,2}/g).map((byte) => parseInt(byte, 16))
    );
    const blob = new Blob([byteArray], { type: 'image/png' });
    const imageUrl = URL.createObjectURL(blob);

    // Update the prediction data with the new image URL
    console.log("Data : ",data);
    setPredictionData({
      ...data,
      image: imageUrl, // Use the Blob URL for image display
      detectionData: data.detection_data,
      imageMetadata: {
        bounds: data.image_bounds,
        crs: data.crs,
      },
    });

    // Clean up the previous uploaded image URL
    if (uploadedImage) {
      URL.revokeObjectURL(uploadedImage);
      setUploadedImage(null);
    }
  };

  const handleImageSelected = (imageUrl) => {
    setUploadedImage(imageUrl);
    setPredictionData(null); // Reset prediction data when a new image is selected
  };

  const handleExport = async (format) => {
    if (!predictionData) {
      alert('No data available to export!');
      return;
    }

    try {
      let fileData;
      let fileName;

      if (format === 'geojson') {
        if (!predictionData.geojson_filename) {
          alert('GeoJSON file not available.');
          return;
        }
        const arrayBuffer = await downloadGeoJSON(predictionData.geojson_filename);
        fileData = new Blob([arrayBuffer], { type: 'application/geo+json' });
        fileName = 'export.geojson';
      } else if (format === 'shapefile') {
        if (!predictionData.shapefile_filename) {
          alert('Shapefile not available.');
          return;
        }
        const arrayBuffer = await downloadShapefile(predictionData.shapefile_filename);
        fileData = new Blob([arrayBuffer], { type: 'application/zip' });
        fileName = 'export.zip';
      }

      const url = window.URL.createObjectURL(fileData);

      // Trigger the download
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', fileName);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url); // Clean up URL
    } catch (error) {
      console.error('Error downloading file:', error);
      alert('Failed to download file.');
    }
  };

  return (
    <Container>
      <div>
        {/* <h2>Tree crown Delination</h2> */}
        <Row>
          <Col lg={3}>
            <ImageUploader
              onUploadSuccess={handleUploadSuccess}
              onImageSelected={handleImageSelected}
              setFileType={setFileType}
            />
          </Col>
          <Col lg={9} >
            <div style={{
              marginTop: '0.7rem',
            }}>
              <ImageViewer fileType={fileType} imageData={predictionData?.image || uploadedImage} />
            </div>
          </Col>
        </Row>
        <div>

          {/* <Chat
            treeCount={predictionData?.tree_count || 0}
            totalArea={predictionData?.total_area || 0.0}
            averageTreeArea={predictionData?.average_tree_area || 0.0}
            imageMetadata={{
              width: predictionData?.image_width || 'N/A',
              height: predictionData?.image_height || 'N/A',
              crs: predictionData?.crs || 'N/A',
              transform: predictionData?.transform || 'N/A',
            }}
          /> */}

          <ExportButton onExport={handleExport} />

        </div>
      </div>
    </Container>
  );
};

export default SatelliteImage;
