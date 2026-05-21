import React from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { jwtDecode } from 'jwt-decode';
import axios from 'axios';
const SignupPageGoogle = ({onSuccessCallBack}) => {
  const googleLogin =  useGoogleLogin({
    onSuccess: async  (credentialResponse) => {
      // console.log('Google login successful', credentialResponse);
      // console.log('Google login successful', credentialResponse.access_token);
      const userInfo = await  axios
        .get('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: { Authorization: `Bearer ${credentialResponse.access_token}` },
        })
        .then(res => res.data);

      // console.log(userInfo);
      localStorage.setItem('loginMethod','google')
      onSuccessCallBack(userInfo);
    },
    onError: () => {
      console.error('Google login failed');
      // Handle login errors here
    },
  })

  return (
    <img
      src="https://img.icons8.com/color/48/000000/google-logo.png"
      style={{
        width: '30px',
        height: 'auto',
        marginRight: '10px',
        cursor: 'pointer',
      }}
      onClick={googleLogin}
    />
  );
};

export default SignupPageGoogle;
