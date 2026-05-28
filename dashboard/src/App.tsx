import { Refine } from "@refinedev/core";
import { RefineThemes, useNotificationProvider } from "@refinedev/antd";
import { dataProvider } from "@refinedev/supabase";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider, App as AntdApp } from "antd";
import heIL from "antd/locale/he_IL";
import { supabaseClient } from "./supabaseClient";
import { ClientUploadPage } from "./pages/ClientUpload";

import "@refinedev/antd/dist/reset.css";

function App() {
  return (
    <BrowserRouter>
      <ConfigProvider theme={RefineThemes.Blue} direction="rtl" locale={heIL}>
        <AntdApp>
          <Refine
            dataProvider={dataProvider(supabaseClient)}
            notificationProvider={useNotificationProvider}
            resources={[
              {
                name: "client-upload",
                list: "/",
              },
            ]}
          >
            <Routes>
              <Route path="/" element={<ClientUploadPage />} />
            </Routes>
          </Refine>
        </AntdApp>
      </ConfigProvider>
    </BrowserRouter>
  );
}

export default App;
