import React from 'react';
import { Row, Col, Card } from 'react-bootstrap';
import UiScopedView from '../../components/UiScopedView';

const ConfigInner = () => {
    return (
        <>
        {/* heading available mobles */}
        <h3>Available Models</h3>
        {/* render a list of 9 llm or ML or Deep Learning modle names which are used for the above mentioned use cases, 3 modles for each feature  */}
        <Row>
          <Col>
            <Card>
              <Card.Header>
                <Card.Title as="h5">LLM Models</Card.Title>
              </Card.Header>
              <Card.Body>
                <Card.Text>
                  <ul>
                    <li>1. GPT-4</li>
                    <li>2. BERT</li>
                    <li>3. T5</li>
                  </ul>
                </Card.Text>
              </Card.Body>
            </Card>
          </Col>
          <Col>
            <Card>
              <Card.Header>
                <Card.Title as="h5">Computer Vision Models</Card.Title>
              </Card.Header>
              <Card.Body>
                <Card.Text>
                  <ul>
                    <li>1. YOLO</li>
                    <li>2. SSD</li>
                    <li>3. Faster R-CNN</li>
                  </ul>
                </Card.Text>
              </Card.Body>
            </Card>
          </Col>
          <Col>
            <Card>
              <Card.Header>
                <Card.Title as="h5">GIS Models</Card.Title>
              </Card.Header>
              <Card.Body>
                <Card.Text>
                  <ul>
                    <li>1. Model A</li>
                    <li>2. Model B</li>
                    <li>3. Model C</li>
                  </ul>
                </Card.Text>
              </Card.Body>
            </Card>
          </Col>
        </Row>
        <h3>More Configurations</h3>
        <Row>
            <Col>
                <Card>
                <Card.Header>
                    <Card.Title as="h5">Computer Vision</Card.Title>
                </Card.Header>
                <Card.Body>
                    <Card.Text>
                    <ul>
                        <li>1. Cam A</li>
                        <li>2. Cam B</li>
                        <li>3. Cam C</li>
                    </ul>
                    </Card.Text>
                </Card.Body>
                </Card>
            </Col>
            {/* <Col>
                <Card>
                <Card.Header>
                    <Card.Title as="h5">Configurations</Card.Title>
                </Card.Header>
                <Card.Body>
                    <Card.Text>
                    <ul>
                        <li>1. Configuration A</li>
                        <li>2. Configuration B</li>
                        <li>3. Configuration C</li>
                    </ul>
                    </Card.Text>
                </Card.Body>
                </Card>
            </Col>
            <Col>
                <Card>
                <Card.Header>
                    <Card.Title as="h5">Configurations</Card.Title>
                </Card.Header>
                <Card.Body>
                    <Card.Text>
                    <ul>
                        <li>1. Configuration A</li>
                        <li>2. Configuration B</li>
                        <li>3. Configuration C</li>
                    </ul>
                    </Card.Text>
                </Card.Body>
                </Card>
            </Col> */}
        </Row>
        </>
    );
    }


export default function Config() {
  return (
    <UiScopedView flag="show_config_page">
      <ConfigInner />
    </UiScopedView>
  );
}