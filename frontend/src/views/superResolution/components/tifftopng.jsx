import React, { useState, useEffect } from "react";
// import Tiff from "tiff.js";
import tiffToPng from "tiff-to-png";

const TiffToPng = ({ tiffBlob }) => {
    console.log(tiffBlob.type)
    console.log(tiffBlob);
    const [imageSrc, setImageSrc] = useState(null);
    const  converttifftopng = async (tiffBlob) => {
        const file = tiffBlob;
        if (file && file.type === "image/tiff") {
            const arrayBuffer = await file.arrayBuffer(); // Convert file to ArrayBuffer
            var converter= new tiffToPng();
            const pngDataUrl = await tiffToPng(arrayBuffer); // Convert TIFF to PNG
            setImageSrc(pngDataUrl);
        } else {
            alert("Please upload a TIFF file.");
        }
    };

    useEffect(() => {
    converttifftopng(tiffBlob);
    }, [tiffBlob]);

    return (
        <div className="flex justify-center items-center">
            <img src={imageSrc} alt="Satellite" />
        </div>
    );
}

export default TiffToPng;