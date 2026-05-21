import React from 'react';
import { useMsal } from '@azure/msal-react';

const SignupPageMicrosoft = ({onSuccessCallBack}) => {
    const { instance } = useMsal();

    const handleLogin = () => {
        instance.loginPopup({
            prompt: "select_account",
            scopes: ["openid", "profile", "User.Read"],
        }).then(response => {
            console.log("Logged in successfully:");
            localStorage.setItem('loginMethod','microsoft')
            onSuccessCallBack(response)
        }).catch(error => {
            console.error("Login failed:", error);
        });
    };

    return (
        <div>
            <button onClick={handleLogin} style={iconButtonStyle}>
                <img
                    src="https://img.icons8.com/color/48/000000/microsoft.png"
                    style={{
                        width: '30px',
                        height: 'auto',
                        marginRight: '7px',
                        cursor: 'pointer',
                    }}
                />
            </button>
        </div>
    );
};

const iconButtonStyle = {
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    padding: 0,
};

const logoStyle = {
    width: '30px',
    height: '30px',
};

export default SignupPageMicrosoft;
